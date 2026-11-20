"""AI-generated test cases for faculty (validated before they reach the editor)."""

from __future__ import annotations

import ast
import json
import re

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.content import TEMPLATES
from app.models import TestCaseSpec
from app.schemas import GenerateTestsResponse

_NAME = re.compile(r"^test_[a-z0-9_]{1,80}$")


class _GenTest(BaseModel):
    name: str
    description: str
    hidden: bool
    code: str
    inputs_json: str
    expected_json: str


class _GenOut(BaseModel):
    tests: list[_GenTest]


def _bits(raw: str) -> dict[str, int] | None:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    if not all(isinstance(k, str) and v in (0, 1) for k, v in data.items()):
        return None
    return {k: int(v) for k, v in data.items()}


def validate_generated(lab_type: str, items: list[_GenTest]) -> list[TestCaseSpec]:
    out: list[TestCaseSpec] = []
    seen: set[str] = set()
    for g in items:
        name = re.sub(r"[^a-z0-9_]", "_", g.name.strip().lower())
        if not name.startswith("test_"):
            name = "test_" + name
        if not _NAME.match(name) or name in seen:
            continue
        if lab_type == "circuit":
            inputs, expected = _bits(g.inputs_json), _bits(g.expected_json)
            if not inputs or not expected:
                continue
            spec = TestCaseSpec(name=name, description=g.description[:300], hidden=g.hidden, inputs=inputs, expected=expected)
        else:
            try:
                ast.parse(g.code)
            except SyntaxError:
                continue
            if not g.code.strip() or "import main" in g.code:
                continue
            spec = TestCaseSpec(name=name, description=g.description[:300], hidden=g.hidden, code=g.code.strip())
        seen.add(name)
        out.append(spec)
    return out[:10]


class TestGenerator:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def generate(self, title: str, description: str, lab_type: str, reference_code: str | None) -> GenerateTestsResponse:
        prompt = (
            f"LAB TYPE: {lab_type}\nTITLE: {title}\nBRIEF:\n{description[:6000]}\n\n"
            + (f"REFERENCE SOLUTION / STARTER (for names and signatures):\n{reference_code[:12000]}\n" if reference_code else "")
        )
        out = await self.ai.gemini_json(system=prompts.TEST_GENERATOR, prompt=prompt, schema=_GenOut, temperature=0.4, max_tokens=4096)
        if out is not None:
            tests = validate_generated(lab_type, out.tests)
            if tests:
                return GenerateTestsResponse(test_cases=tests, model=self.ai.gemini_model, source="gemini")
        template = TEMPLATES[lab_type]["test_cases"]
        return GenerateTestsResponse(test_cases=[t.model_copy() for t in template], model="template", source="fallback")
