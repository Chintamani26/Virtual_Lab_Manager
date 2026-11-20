"""Lab adapters (coding / circuit / notebook / worksheet) behind one unified ExecutionService."""

from __future__ import annotations

import json
import time

from app.execution.base import (
    ExecutionRequest,
    ExecutionResult,
    LabAdapter,
    PythonRunner,
    TruthTableRow,
    clip,
)
from app.execution.circuit_sim import CircuitError, parse_circuit
from app.execution.harness import build_harness, cells_from_report, parse_report, results_from_report
from app.models import TestResult

MAX_SOURCE_BYTES = 200_000


class ExecutionInputError(ValueError):
    """Raised for malformed lab files (mapped to HTTP 422)."""


def _require_file(files: dict[str, str], filename: str) -> str:
    if filename not in files:
        raise ExecutionInputError(f"missing required file '{filename}'")
    src = files[filename]
    if len(src.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ExecutionInputError(f"'{filename}' exceeds {MAX_SOURCE_BYTES // 1000} KB")
    return src


def _load_failure_message(status: str, stderr: str) -> str:
    if status == "timeout":
        return "Time limit exceeded — check for infinite loops or unbounded recursion"
    tail = stderr.strip().splitlines()[-1:] if stderr.strip() else []
    return "Execution failed" + (f": {tail[0]}" if tail else "")


class CodingAdapter(LabAdapter):
    lab_type = "coding"
    filename = "main.py"

    def __init__(self, runner: PythonRunner) -> None:
        self.runner = runner

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        source = _require_file(req.files, self.filename)
        if req.mode == "run":
            raw = await self.runner.run(source)
            return ExecutionResult(
                engine=raw.engine, lab_type="coding", mode="run", status=raw.status,
                stdout=raw.stdout, stderr=raw.stderr, duration_ms=raw.duration_ms,
            ).finalize()

        program, marker = build_harness(kind="module", mode="test", tests=req.tests, source=source)
        raw = await self.runner.run(program)
        report, stdout = parse_report(raw.stdout, marker)
        tests = results_from_report(report, req.tests, _load_failure_message(raw.status, raw.stderr))
        status = raw.status
        if report and report.get("load_error"):
            status = "compile_error" if report["load_error"].startswith("SyntaxError") else "error"
        elif report is not None and status == "error":
            status = "ok"  # harness finished; non-zero exit came from elsewhere
        student_stdout = (report or {}).get("stdout", "") if report else stdout
        return ExecutionResult(
            engine=raw.engine, lab_type="coding", mode="test", status=status,
            stdout=clip(student_stdout), stderr=raw.stderr, tests=tests, duration_ms=raw.duration_ms,
        ).finalize()


class NotebookAdapter(LabAdapter):
    lab_type = "notebook"
    filename = "data.ipynb"

    def __init__(self, runner: PythonRunner) -> None:
        self.runner = runner

    @staticmethod
    def code_cells(nb_json: str) -> list[tuple[int, str]]:
        try:
            nb = json.loads(nb_json)
            cells = nb["cells"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ExecutionInputError(f"data.ipynb is not a valid notebook: {exc}") from exc
        out = []
        for idx, cell in enumerate(cells):
            if cell.get("cell_type") != "code":
                continue
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            # neutralise IPython magics / shell escapes, which plain Python cannot run
            lines = [("# " + ln) if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines()]
            out.append((idx, "\n".join(lines)))
        return out

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        cells = self.code_cells(_require_file(req.files, self.filename))
        program, marker = build_harness(kind="notebook", mode=req.mode, tests=req.tests, cells=cells)
        raw = await self.runner.run(program)
        report, stdout = parse_report(raw.stdout, marker)
        tests = (
            results_from_report(report, req.tests, _load_failure_message(raw.status, raw.stderr))
            if req.mode == "test"
            else []
        )
        status = raw.status
        if report is not None:
            status = "error" if report.get("load_error") else "ok"
        return ExecutionResult(
            engine=raw.engine, lab_type="notebook", mode=req.mode, status=status,
            stdout=clip(stdout), stderr=raw.stderr if report is None else (report.get("load_error") or ""),
            tests=tests, duration_ms=raw.duration_ms, cell_outputs=cells_from_report(report),
        ).finalize()


class CircuitAdapter(LabAdapter):
    lab_type = "circuit"
    filename = "circuit.sim"
    engine = "circuit-sim"

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        source = _require_file(req.files, self.filename)
        started = time.perf_counter()
        try:
            circuit = parse_circuit(source)
            table = circuit.truth_table()
        except CircuitError as exc:
            where = f" (line {exc.line})" if exc.line else ""
            msg = f"CircuitError: {exc.message}{where}"
            tests = [TestResult(name=t.name, passed=False, message=msg, hidden=t.hidden) for t in req.tests]
            return ExecutionResult(
                engine=self.engine, lab_type="circuit", mode=req.mode, status="compile_error",
                stderr=msg, tests=tests if req.mode == "test" else [],
                duration_ms=int((time.perf_counter() - started) * 1000),
            ).finalize()

        header = circuit.inputs + ["|"] + circuit.outputs
        lines = [
            f"Circuit OK: {len(circuit.inputs)} inputs, {len(circuit.outputs)} outputs, {circuit.gate_count} gates",
            "",
            " ".join(f"{h:>4}" for h in header),
        ]
        for ins, outs in table:
            lines.append(" ".join(f"{v:>4}" for v in [*ins.values(), "|", *outs.values()]))

        tests: list[TestResult] = []
        if req.mode == "test":
            for t in req.tests:
                try:
                    given = {k: int(v) for k, v in (t.inputs or {}).items()}
                    missing = [i for i in circuit.inputs if i not in given]
                    if missing:
                        raise CircuitError(f"test does not set input(s) {', '.join(missing)}")
                    got = circuit.evaluate({k: given[k] for k in circuit.inputs})
                    wrong = []
                    for sig, exp in (t.expected or {}).items():
                        if sig not in got:
                            wrong.append(f"output '{sig}' is not declared in OUTPUT")
                        elif got[sig] != int(exp):
                            wrong.append(f"{sig} expected {exp}, got {got[sig]}")
                    ins = ", ".join(f"{k}={v}" for k, v in given.items())
                    tests.append(
                        TestResult(
                            name=t.name, passed=not wrong, hidden=t.hidden,
                            message=None if not wrong else f"for {ins}: " + "; ".join(wrong),
                        )
                    )
                except CircuitError as exc:
                    tests.append(TestResult(name=t.name, passed=False, message=exc.message, hidden=t.hidden))

        return ExecutionResult(
            engine=self.engine, lab_type="circuit", mode=req.mode, status="ok",
            stdout="\n".join(lines), tests=tests,
            truth_table=[TruthTableRow(inputs=i, outputs=o) for i, o in table],
            duration_ms=int((time.perf_counter() - started) * 1000),
        ).finalize()


# Helpers available to worksheet check code. Python 3.8 compatible (Judge0 CE). The student's answers are embedded as
# a JSON string literal (repr of a str), so nothing they type is ever executed as code.
WORKSHEET_PRELUDE = r'''
import json as _json, math
_ANSWERS = _json.loads(__ANSWERS__)
STEPS = _ANSWERS.get("steps") or {}
ROWS = _ANSWERS.get("rows") or []

def _num(raw, what):
    s = str("" if raw is None else raw).strip().replace("\u2212", "-").replace("\u2013", "-")
    if s == "":
        raise AssertionError(what + " is empty")
    try:
        return float(s)
    except ValueError:
        raise AssertionError("%s must be a number (got %r)" % (what, s))

def answer(key, label=None):
    """The student's answer for a step, as a number."""
    return _num(STEPS.get(key), label or key)

def readings(min_rows=1):
    if len(ROWS) < min_rows:
        raise AssertionError("Record at least %d readings in the observation table (you have %d)" % (min_rows, len(ROWS)))
    return ROWS

def column(key, label=None):
    """One column of the observation table, as numbers."""
    if not ROWS:
        raise AssertionError("No readings recorded yet")
    return [_num(r.get(key), "%s in reading %d" % (label or key, i + 1)) for i, r in enumerate(ROWS)]

def near(value, expected, tol):
    return abs(value - expected) <= tol

def near_rel(value, expected, rel):
    return abs(value - expected) <= abs(expected) * rel

def fit_line(xs, ys):
    """Least-squares slope and intercept."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise AssertionError("The readings need at least two different values to fit a line")
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return m, my - m * mx
'''

MAX_WORKSHEET_ROWS = 30
MAX_WORKSHEET_VALUE_CHARS = 40


def parse_answers(raw: str) -> dict:
    """Validate answers.json: {"steps": {id: value}, "rows": [{key: value}]} with short scalar values."""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ExecutionInputError(f"answers.json is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ExecutionInputError("answers.json must be an object")
    steps, rows = data.get("steps") or {}, data.get("rows") or []
    if not isinstance(steps, dict) or not isinstance(rows, list) or len(rows) > MAX_WORKSHEET_ROWS:
        raise ExecutionInputError("answers.json must have a 'steps' object and at most 30 'rows'")

    def scalar(v) -> bool:
        return v is None or isinstance(v, (int, float)) or (isinstance(v, str) and len(v) <= MAX_WORKSHEET_VALUE_CHARS)

    if len(steps) > 100 or not all(isinstance(k, str) and scalar(v) for k, v in steps.items()):
        raise ExecutionInputError("answers.json 'steps' must map step ids to short values")
    for r in rows:
        if not isinstance(r, dict) or len(r) > 12 or not all(isinstance(k, str) and scalar(v) for k, v in r.items()):
            raise ExecutionInputError("each answers.json row must map column keys to short values")
    return {"steps": steps, "rows": rows}


class WorksheetAdapter(LabAdapter):
    """Maths worksheets and virtual experiments: numeric answers, checked by test code in the sandbox."""

    lab_type = "worksheet"
    filename = "answers.json"

    def __init__(self, runner: PythonRunner) -> None:
        self.runner = runner

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        answers = parse_answers(_require_file(req.files, self.filename))
        if req.mode == "run":  # nothing to run: the worksheet is only checked
            return ExecutionResult(engine=self.runner.name, lab_type="worksheet", mode="run", status="ok",
                                   stdout="Answers saved.").finalize()
        source = WORKSHEET_PRELUDE.replace("__ANSWERS__", repr(json.dumps(answers)))
        program, marker = build_harness(kind="module", mode="test", tests=req.tests, source=source)
        raw = await self.runner.run(program)
        report, _ = parse_report(raw.stdout, marker)
        tests = results_from_report(report, req.tests, _load_failure_message(raw.status, raw.stderr))
        status = "error" if report and report.get("load_error") else ("ok" if report is not None else raw.status)
        return ExecutionResult(
            engine=raw.engine, lab_type="worksheet", mode="test", status=status,
            stderr=raw.stderr if status != "ok" else "", tests=tests, duration_ms=raw.duration_ms,
        ).finalize()


class ExecutionService:
    def __init__(self, runner: PythonRunner) -> None:
        self.runner = runner
        self.adapters: dict[str, LabAdapter] = {
            "coding": CodingAdapter(runner),
            "circuit": CircuitAdapter(),
            "notebook": NotebookAdapter(runner),
            "worksheet": WorksheetAdapter(runner),
        }

    @property
    def engine_name(self) -> str:
        return self.runner.name

    async def execute(self, req: ExecutionRequest) -> ExecutionResult:
        adapter = self.adapters.get(req.lab_type)
        if adapter is None:
            raise ExecutionInputError(f"unsupported lab type '{req.lab_type}'")
        return await adapter.execute(req)
