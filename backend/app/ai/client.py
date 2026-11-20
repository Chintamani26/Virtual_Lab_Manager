"""Thin async wrapper over the google-genai SDK for the hybrid Gemma + Gemini pipeline.

* Gemini (GEMINI_MODEL): structured JSON output via response_schema — Socratic hints,
  rubric grading, test generation, HOD analytics.
* Gemma (GEMMA_MODEL): fast, cheap lint pass. JSON mode isn't guaranteed for Gemma on the
  Gemini API, so we ask for JSON in the prompt and parse leniently.

Every call returns None on failure so callers can fall back to deterministic logic and the
demo never breaks when the key is missing, rate-limited or the network is down.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# Redact credentials that might appear inside upstream HTTP/SDK exception strings.
_SECRET_RE = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|bearer\s+|(?:api[_-]?key|key|token)\s*[=:]\s*)[^\s&'\",;]+"
)
# Transient Gemini errors ("503 UNAVAILABLE: model is experiencing high demand", 500 INTERNAL) are retried
# briefly before falling back. Quota (429) and auth errors are not: retrying wouldn't help.
_RETRY_DELAYS_S = (1.0, 2.5)


def _transient(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)[:200]
    return code in (500, 503, 504) or "UNAVAILABLE" in text or "503" in text[:20] or "DEADLINE_EXCEEDED" in text


def extract_json(text: str) -> str:
    """Best-effort extraction of the first JSON object from model text."""
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in model output")
    return text[start : end + 1]


class AIClient:
    def __init__(self, settings: Settings) -> None:
        self.gemini_model = settings.gemini_model
        self.gemma_model = settings.gemma_model
        self.enabled = settings.ai_enabled
        self._api_key = settings.gemini_api_key
        self.last_error: str | None = None  # shown on the public /api/health endpoint, so always redacted
        self._client = None
        self._types = None
        if self.enabled:
            from google import genai
            from google.genai import types

            self._types = types
            self._client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(settings.ai_timeout_seconds * 1000)),
            )

    async def gemini_json(
        self, *, system: str, prompt: str, schema: type[T], temperature: float = 0.3, max_tokens: int = 2048,
        timeout_s: float | None = None,
    ) -> T | None:
        """`timeout_s` overrides AI_TIMEOUT_SECONDS for long generations (e.g. a whole practical)."""
        if not self.enabled:
            return None
        types = self._types
        try:
            resp = await self._generate(
                model=self.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(  # type: ignore[union-attr]
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                    response_schema=schema,
                    http_options=types.HttpOptions(timeout=int(timeout_s * 1000)) if timeout_s else None,  # type: ignore[union-attr]
                ),
            )
            parsed = getattr(resp, "parsed", None)
            if isinstance(parsed, schema):
                return parsed
            if isinstance(parsed, dict):
                return schema.model_validate(parsed)
            return schema.model_validate_json(extract_json(resp.text or ""))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            self._record("gemini (invalid output)", exc)
        except Exception as exc:  # network / quota / auth — never break the request
            self._record("gemini", exc)
        return None

    async def gemma_json(self, *, system: str, prompt: str, schema: type[T], max_tokens: int = 800) -> T | None:
        if not self.enabled:
            return None
        types = self._types
        try:
            resp = await self._generate(
                model=self.gemma_model,
                contents=prompt,
                config=types.GenerateContentConfig(  # type: ignore[union-attr]
                    system_instruction=system, temperature=0.1, max_output_tokens=max_tokens
                ),
            )
            return schema.model_validate_json(extract_json(resp.text or ""))
        except Exception as exc:
            self._record("gemma", exc)
        return None

    async def _generate(self, **kwargs):
        for delay in (*_RETRY_DELAYS_S, None):
            try:
                return await self._client.aio.models.generate_content(**kwargs)  # type: ignore[union-attr]
            except Exception as exc:
                if delay is None or not _transient(exc):
                    raise
                log.info("Gemini transient error (%s); retrying in %.1fs", self._redact(str(exc))[:80], delay)
                await asyncio.sleep(delay)

    def _redact(self, text: str) -> str:
        """SDK/HTTP error text can echo request details; make sure the API key never reaches logs or /api/health."""
        cleaned = text.replace(self._api_key, "[REDACTED]") if self._api_key else text
        return _SECRET_RE.sub(r"\1[REDACTED]", cleaned)

    def _record(self, which: str, exc: Exception) -> None:
        self.last_error = f"{which}: {type(exc).__name__}: {self._redact(str(exc))[:300]}"
        log.warning("AI call failed (%s) — using fallback", self.last_error)
