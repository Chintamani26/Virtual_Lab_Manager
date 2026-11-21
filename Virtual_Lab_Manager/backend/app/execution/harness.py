"""Builds a self-contained Python 3.8+ test harness and parses its structured report.

The harness is a single program (so it works identically on Judge0 and the local runner):
  1. decodes a base64 JSON payload (student source / notebook cells + test code),
  2. executes the student code in its own namespace (`__name__ != "__main__"` in test mode),
  3. runs each test with a per-test alarm, catching assertion/runtime errors,
  4. prints one marker-prefixed JSON line with results to the real stdout.
"""

from __future__ import annotations

import base64
import json
import secrets

from app.execution.base import CellOutput
from app.models import TestCaseSpec, TestResult

# NOTE: must stay compatible with Python 3.8 (Judge0 CE language 71).
_HARNESS_TEMPLATE = r'''
import base64 as _b64, contextlib as _ctx, io as _io, json as _json, sys as _sys, traceback as _tb

def _vlm_main(_payload_b64, _marker):
    _p = _json.loads(_b64.b64decode(_payload_b64).decode("utf-8"))
    _real_out = _sys.__stdout__
    _ns = {"__name__": "__student__", "__builtins__": __builtins__}
    _report = {"load_error": None, "cells": [], "tests": [], "stdout": ""}

    def _describe(exc):
        if isinstance(exc, SyntaxError):
            return "SyntaxError: %s (%s line %s)" % (exc.msg, exc.filename, exc.lineno)
        frames = [f for f in _tb.extract_tb(exc.__traceback__) if f.filename == "main.py" or f.filename.startswith("cell[")]
        where = (" (%s line %d)" % (frames[-1].filename, frames[-1].lineno)) if frames else ""
        return "%s: %s%s" % (type(exc).__name__, exc, where)

    try:
        import signal as _signal
        def _alarm(signum, frame):
            raise TimeoutError("test exceeded %ss time limit" % _p["per_test_timeout"])
        _signal.signal(_signal.SIGALRM, _alarm)
        _has_alarm = True
    except Exception:
        _has_alarm = False

    def _run(code, filename):
        if _has_alarm:
            _signal.setitimer(_signal.ITIMER_REAL, _p["per_test_timeout"])
        try:
            exec(compile(code, filename, "exec"), _ns)
        finally:
            if _has_alarm:
                _signal.setitimer(_signal.ITIMER_REAL, 0)

    # --- 1. load student code -------------------------------------------------------
    if _p["kind"] == "module":
        _buf = _io.StringIO()
        try:
            with _ctx.redirect_stdout(_buf):
                _run(_p["source"], "main.py")
        except SystemExit:
            pass
        except BaseException as e:
            _report["load_error"] = _describe(e)
            _tb.print_exc(file=_sys.stderr)
        _report["stdout"] = _buf.getvalue()
    else:  # notebook: run code cells top-to-bottom, stop at first error
        _failed = False
        for _idx, _src in _p["cells"]:
            if _failed:
                _report["cells"].append({"index": _idx, "stdout": "", "error": "skipped: an earlier cell failed"})
                continue
            _buf = _io.StringIO()
            _err = None
            try:
                with _ctx.redirect_stdout(_buf):
                    _run(_src, "cell[%d]" % _idx)
            except SystemExit:
                pass
            except BaseException as e:
                _err = _describe(e)
                _failed = True
                _report["load_error"] = "cell %d failed: %s" % (_idx, _err)
            _report["cells"].append({"index": _idx, "stdout": _buf.getvalue(), "error": _err})

    # --- 2. run tests ------------------------------------------------------------------
    if _p["mode"] == "test":
        _base = dict(_ns)
        for _name, _code in _p["tests"]:
            if _report["load_error"] and _p["kind"] == "module":
                _report["tests"].append({"name": _name, "passed": False, "message": "main.py failed to load: " + _report["load_error"]})
                continue
            _ns.clear(); _ns.update(_base)
            _buf = _io.StringIO()
            try:
                with _ctx.redirect_stdout(_buf):
                    _run(_code, _name)
                _report["tests"].append({"name": _name, "passed": True, "message": None})
            except AssertionError as e:
                _msg = str(e)
                if not _msg:
                    _fr = [f for f in _tb.extract_tb(e.__traceback__) if f.filename == _name]
                    _lines = _code.splitlines()
                    _msg = ("failed: " + _lines[_fr[-1].lineno - 1].strip()) if _fr and _fr[-1].lineno <= len(_lines) else "assertion failed"
                _report["tests"].append({"name": _name, "passed": False, "message": "AssertionError: " + _msg})
            except BaseException as e:
                _report["tests"].append({"name": _name, "passed": False, "message": _describe(e)})

    _real_out.write("\n" + _marker + _json.dumps(_report) + "\n")
    _real_out.flush()

_vlm_main("__PAYLOAD__", "__MARKER__")
'''


def build_harness(
    *,
    kind: str,
    mode: str,
    tests: list[TestCaseSpec],
    source: str = "",
    cells: list[tuple[int, str]] | None = None,
    per_test_timeout: float = 2.0,
) -> tuple[str, str]:
    """Return (program_source, marker)."""
    marker = f"__VLM_REPORT_{secrets.token_hex(8)}__"
    payload = {
        "kind": kind,
        "mode": mode,
        "source": source,
        "cells": cells or [],
        "tests": [(t.name, t.code or "") for t in tests],
        "per_test_timeout": per_test_timeout,
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    program = _HARNESS_TEMPLATE.replace("__PAYLOAD__", encoded).replace("__MARKER__", marker)
    return program, marker


def parse_report(stdout: str, marker: str) -> tuple[dict | None, str]:
    """Extract the harness JSON report; returns (report_or_None, stdout_without_report)."""
    idx = stdout.rfind(marker)
    if idx == -1:
        return None, stdout
    line_end = stdout.find("\n", idx)
    raw = stdout[idx + len(marker) : line_end if line_end != -1 else None]
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return None, stdout[:idx]
    return report, stdout[:idx].rstrip("\n")


def results_from_report(report: dict | None, tests: list[TestCaseSpec], failure_message: str) -> list[TestResult]:
    hidden = {t.name: t.hidden for t in tests}
    if report is None:
        return [TestResult(name=t.name, passed=False, message=failure_message, hidden=t.hidden) for t in tests]
    seen = {r["name"]: r for r in report.get("tests", [])}
    out = []
    for t in tests:
        r = seen.get(t.name)
        if r is None:
            out.append(TestResult(name=t.name, passed=False, message=failure_message, hidden=t.hidden))
        else:
            out.append(TestResult(name=t.name, passed=bool(r["passed"]), message=r.get("message"), hidden=hidden[t.name]))
    return out


def cells_from_report(report: dict | None) -> list[CellOutput] | None:
    if not report:
        return None
    return [CellOutput(**c) for c in report.get("cells", [])]
