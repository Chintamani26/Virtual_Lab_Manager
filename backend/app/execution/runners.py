"""Python sandbox runners: Judge0 (production) and a local subprocess runner (development only)."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx

from app.config import Settings
from app.execution.base import PythonRunner, RawRunResult, clip

log = logging.getLogger(__name__)

# Judge0 status ids: https://ce.judge0.com/#statuses-and-languages-status-get
_J0_QUEUED = {1, 2}
_J0_ACCEPTED = 3
_J0_TLE = 5
_J0_COMPILE = 6


def _b64e(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _b64d(s: str | None) -> str:
    if not s:
        return ""
    return base64.b64decode(s).decode("utf-8", errors="replace")


class Judge0Runner(PythonRunner):
    name = "judge0"

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.judge0_url.rstrip("/")
        self.language_id = settings.judge0_python_language_id
        self.timeout = settings.execution_timeout_seconds
        self.headers = {"Content-Type": "application/json"}
        if settings.judge0_rapidapi_host:
            self.headers["X-RapidAPI-Key"] = settings.judge0_api_key
            self.headers["X-RapidAPI-Host"] = settings.judge0_rapidapi_host
        elif settings.judge0_api_key:
            self.headers["X-Auth-Token"] = settings.judge0_api_key

    async def run(self, source: str, stdin: str = "") -> RawRunResult:
        payload = {
            "source_code": _b64e(source),
            "language_id": self.language_id,
            "stdin": _b64e(stdin),
            "cpu_time_limit": self.timeout,
            "wall_time_limit": self.timeout * 2,
            "memory_limit": 256_000,
        }
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout * 3 + 10, headers=self.headers) as client:
            resp = await client.post(
                f"{self.base_url}/submissions", params={"base64_encoded": "true", "wait": "true"}, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            # wait=true may still return a queued submission on busy instances -> poll.
            deadline = time.monotonic() + self.timeout * 4
            while data.get("status", {}).get("id") in _J0_QUEUED or "status" not in data:
                if time.monotonic() > deadline:
                    return RawRunResult(status="timeout", stderr="Judge0 queue timeout", engine=self.name)
                await asyncio.sleep(0.6)
                token = data["token"]
                r = await client.get(
                    f"{self.base_url}/submissions/{token}",
                    params={"base64_encoded": "true", "fields": "stdout,stderr,compile_output,message,status,time,exit_code,token"},
                )
                r.raise_for_status()
                data = r.json()

        status_id = data["status"]["id"]
        stdout = _b64d(data.get("stdout"))
        stderr = _b64d(data.get("stderr")) or _b64d(data.get("compile_output"))
        if status_id not in (_J0_ACCEPTED,) and not stderr:
            stderr = _b64d(data.get("message")) or data["status"].get("description", "")
        status = "ok"
        if status_id == _J0_TLE:
            status = "timeout"
        elif status_id == _J0_COMPILE:
            status = "compile_error"
        elif status_id != _J0_ACCEPTED:
            status = "error"
        wall_ms = int((time.perf_counter() - started) * 1000)
        cpu_ms = int(float(data.get("time") or 0) * 1000)
        return RawRunResult(
            stdout=clip(stdout),
            stderr=clip(stderr),
            exit_code=data.get("exit_code"),
            status=status,
            duration_ms=cpu_ms or wall_ms,
            engine=self.name,
        )


def _apply_limits(cpu_seconds: int) -> None:  # pragma: no cover - runs in the child process
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        except (ValueError, OSError):
            pass  # not supported on macOS
    except (ImportError, ValueError, OSError):
        pass  # non-POSIX or constrained container where rlimits cannot be lowered


class LocalSubprocessRunner(PythonRunner):
    """Runs code in a separate, isolated Python process with CPU/time limits.

    NOT a security sandbox — for local development and demos only. Production should use Judge0.
    """

    name = "local-python"

    def __init__(self, settings: Settings) -> None:
        self.timeout = settings.execution_timeout_seconds

    async def run(self, source: str, stdin: str = "") -> RawRunResult:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="vlm-run-") as tmp:
            script = Path(tmp) / "program.py"
            script.write_text(source, encoding="utf-8")
            env = {"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", ""), "HOME": tmp}
            cpu = int(self.timeout) + 1
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(script),
                cwd=tmp,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=(lambda: _apply_limits(cpu)) if os.name == "posix" else None,
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(stdin.encode()), timeout=self.timeout)
                status = "ok" if proc.returncode == 0 else "error"
            except (asyncio.TimeoutError, TimeoutError):
                proc.kill()
                out, err = await proc.communicate()
                status = "timeout"
                err = (err or b"") + f"\nTime limit exceeded ({self.timeout:.0f}s)".encode()
        return RawRunResult(
            stdout=clip(out.decode("utf-8", errors="replace")),
            stderr=clip(err.decode("utf-8", errors="replace")),
            exit_code=proc.returncode,
            status=status,
            duration_ms=int((time.perf_counter() - started) * 1000),
            engine=self.name,
        )


def build_runner(settings: Settings) -> PythonRunner:
    engine = settings.execution_engine
    if engine == "judge0" or (engine == "auto" and settings.judge0_url):
        if not settings.judge0_url:
            raise RuntimeError("EXECUTION_ENGINE=judge0 requires JUDGE0_URL")
        return Judge0Runner(settings)
    if settings.app_env == "production" and not settings.allow_local_execution_in_production:
        raise RuntimeError(
            "Refusing to run student code in local subprocesses in production. "
            "Configure JUDGE0_URL (recommended) or set ALLOW_LOCAL_EXECUTION_IN_PRODUCTION=true for a demo."
        )
    log.warning("Using LocalSubprocessRunner — not a security sandbox; configure Judge0 for production.")
    return LocalSubprocessRunner(settings)
