"""Restricted lab context for the AI Lab Tutor.

Built from an allowlist. The model may see:
  lab title and brief, worksheet instructions (section text and step labels), the student's own current files,
  the visible test cases (worksheet checks: description only), the visible results of the student's latest
  server-side test run, and the last HISTORY_TURNS messages of the server-side conversation.
It never sees: hidden tests (code, names or results), the rubric, worksheet check code (it holds the expected
values), instrument constants, SEB keys, other students' work.

`secret_values` / `hidden_names` are used by the response validator only and are never rendered into a prompt.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

from app.models import ExecutionLogRecord, PracticalRecord, TestCaseSpec, TestResult, TutorMessage

HISTORY_TURNS = 6
# `near(answer('step', 'label'), expected, tolerance)` — labels may contain parentheses, e.g. "f(x₀)"
_NEAR = re.compile(r"near\(\s*answer\(.*?\)\s*,\s*(-?[\d.]+(?:e-?\d+)?)\s*,\s*(-?[\d.]+(?:e-?\d+)?)\s*\)")


def new_nonce() -> str:
    return secrets.token_hex(4).upper()


def fence(name: str, body: str, nonce: str) -> str:
    """Wrap untrusted text in a data block whose closing tag can't be forged (random per-request nonce)."""
    body = body.replace(nonce, "")
    return f"<<{name} {nonce}>>\n{body.strip() or '(empty)'}\n<</{name} {nonce}>>"


def _cap(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + f"\n… [{len(text) - n} more characters]"


@dataclass
class LabContext:
    practical: PracticalRecord
    files: dict[str, str]
    execution: ExecutionLogRecord | None
    history: list[TutorMessage] = field(default_factory=list)
    results_stale: bool = False  # the student's files changed after their last test run

    @property
    def worksheet(self) -> bool:
        return self.practical.lab_type == "worksheet"

    @property
    def visible_tests(self) -> list[TestCaseSpec]:
        return [t for t in self.practical.test_cases if not t.hidden]

    @property
    def hidden_names(self) -> set[str]:
        return {t.name for t in self.practical.test_cases if t.hidden}

    @property
    def results(self) -> list[TestResult]:
        if self.execution is None:
            return []
        hidden = self.hidden_names
        return [r for r in self.execution.test_results if not r.hidden and r.name not in hidden]

    @property
    def failing(self) -> list[TestResult]:
        return [r for r in self.results if not r.passed]

    @property
    def all_passing(self) -> bool:
        return bool(self.results) and not self.failing

    def test(self, name: str | None) -> TestCaseSpec | None:
        return next((t for t in self.visible_tests if t.name == name), None) if name else None

    def result(self, name: str | None) -> TestResult | None:
        return next((r for r in self.results if r.name == name), None) if name else None

    def focus_test(self, requested: str | None = None) -> str | None:
        """The test a reply is about: the requested visible test, else the first failing one, else the first."""
        if self.test(requested):
            return requested
        if self.failing:
            return self.failing[0].name
        return self.visible_tests[0].name if self.visible_tests else None

    def secret_values(self) -> list[tuple[float, float]]:
        """Worksheet: (expected, tolerance) of every check the student hasn't passed yet. Validator only."""
        if not self.worksheet:
            return []
        passed = {r.name for r in self.results if r.passed}
        out = []
        for t in self.practical.test_cases:
            if t.name in passed or not t.code:
                continue
            for m in _NEAR.finditer(t.code):
                out.append((float(m.group(1)), abs(float(m.group(2)))))
        return out

    def visible_text(self) -> str:
        """Everything the student can already read on the lab page (numbers in it are never redacted)."""
        parts = [self.practical.title, self.practical.description]
        for t in self.visible_tests:
            parts.append(t.description)
            if not self.worksheet and t.code:
                parts.append(t.code)
        parts += [r.message or "" for r in self.results]
        parts += self._worksheet_lines()
        parts += list(self.files.values())
        return "\n".join(parts)

    # ---------------------------------------------------------------- rendering
    def _worksheet_lines(self) -> list[str]:
        ws = self.practical.worksheet
        if ws is None:
            return []
        hidden = self.hidden_names
        lines: list[str] = []
        for sec in ws.sections:
            lines.append(f"## {sec.title}\n{sec.body}")
            for st in sec.steps:
                unit = f" ({st.unit})" if st.unit else ""
                checked = f" [checked by {st.test}]" if st.test and st.test not in hidden else ""
                lines.append(f"- step {st.id}: {st.label}{unit}{checked}")
        if ws.table:
            cols = ", ".join(f"{c.label}{f' ({c.unit})' if c.unit else ''}" for c in ws.table.columns)
            lines.append(f"Observation table '{ws.table.title}' ({ws.table.min_rows}-{ws.table.max_rows} rows): {cols}")
        if ws.graph:
            lines.append(f"Graph: {ws.graph.y_label} against {ws.graph.x_label}")
        return lines

    def _tests_block(self) -> str:
        lines = []
        for t in self.visible_tests[:12]:
            lines.append(f"### {t.name}: {t.description}".rstrip(": "))
            if self.worksheet:
                continue  # check code holds the expected value
            if t.code:
                lines.append(_cap(t.code, 1200))
            elif t.inputs is not None:
                lines.append(f"inputs {t.inputs} -> expected {t.expected}")
        return "\n".join(lines)

    def _run_block(self) -> str:
        e = self.execution
        if e is None:
            return "No test run yet."
        lines = [f"{sum(r.passed for r in self.results)} of {len(self.results)} visible tests passed "
                 f"(status {e.status})."]
        if self.results_stale:
            lines.append("NOTE: the student has edited their files since this run; the results may be out of date.")
        for r in self.results:
            lines.append(f"- {'PASS' if r.passed else 'FAIL'} {r.name}" + (f": {_cap(r.message, 300)}" if r.message and not r.passed else ""))
        if e.stderr.strip():
            lines.append("stderr (tail):\n" + e.stderr.strip()[-1500:])
        if e.stdout.strip() and not self.worksheet:
            lines.append("stdout (tail):\n" + e.stdout.strip()[-600:])
        return "\n".join(lines)

    def _history_block(self) -> str:
        out = []
        for m in self.history[-HISTORY_TURNS:]:
            text = m.content if m.role == "student" else (m.content + (f"\nQuestion: {m.guiding_question}" if m.guiding_question else ""))
            tag = "concept-check " if m.action == "concept_check" and m.role == "tutor" and m.understanding is None else ""
            out.append(f"{m.role.upper()} ({tag}{m.action}): {_cap(text, 700)}")
        return "\n".join(out) or "(no earlier messages)"

    def render(self, nonce: str, *, student_message: str | None) -> str:
        p = self.practical
        files = "\n\n".join(f"### {name}\n{_cap(src, 10_000)}" for name, src in self.files.items())
        brief = f"Title: {p.title}\nLab type: {p.lab_type}\n\n{_cap(p.description, 4000)}"
        if self.worksheet:
            brief += "\n\nWorksheet:\n" + "\n".join(self._worksheet_lines())
        blocks = [
            fence("lab", brief, nonce),
            fence("student_files" if not self.worksheet else "student_answers", files, nonce),
            fence("visible_tests", self._tests_block(), nonce),
            fence("last_test_run", self._run_block(), nonce),
            fence("conversation", self._history_block(), nonce),
        ]
        if student_message:
            blocks.append(fence("student_message", student_message, nonce))
        return "\n\n".join(blocks)
