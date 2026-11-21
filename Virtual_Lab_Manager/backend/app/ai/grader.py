"""Automated rubric grading (Gemini) with deterministic guardrails and a heuristic fallback."""

from __future__ import annotations

import ast
import json

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.execution.base import ExecutionResult
from app.models import PracticalRecord, RubricScore

CORRECTNESS_IDS = {"correctness"}


class _CriterionOut(BaseModel):
    criterion_id: str
    score: float
    feedback: str


class _GradeOut(BaseModel):
    criteria: list[_CriterionOut]
    summary: str


class GradeResult(BaseModel):
    breakdown: list[RubricScore]
    total: float
    summary: str
    model: str


def _half(x: float) -> float:
    return round(x * 2) / 2


def _quality_signals(practical: PracticalRecord, files: dict[str, str], result: ExecutionResult) -> tuple[float, list[str]]:
    """Cheap static heuristics -> (score 0..1, notes)."""
    notes: list[str] = []
    score = 0.7
    if practical.lab_type == "coding":
        src = files.get("main.py", "")
        if "TODO" in src:
            score -= 0.2
            notes.append("leftover TODO comments")
        try:
            tree = ast.parse(src)
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            documented = sum(1 for f in funcs if ast.get_docstring(f))
            if funcs and documented / len(funcs) >= 0.3:
                score += 0.2
            else:
                notes.append("few docstrings")
            if any(len(line) > 110 for line in src.splitlines()):
                score -= 0.1
                notes.append("very long lines")
        except SyntaxError:
            score = 0.2
            notes.append("syntax errors")
    elif practical.lab_type == "worksheet":
        try:
            data = json.loads(files.get("answers.json", "") or "{}")
        except json.JSONDecodeError:
            data = {}
        spec = practical.worksheet
        wanted = [s.id for sec in (spec.sections if spec else []) for s in sec.steps]
        steps = data.get("steps") if isinstance(data, dict) else None
        steps = steps if isinstance(steps, dict) else {}
        answered = sum(1 for k in wanted if str(steps.get(k, "") or "").strip())
        frac = answered / len(wanted) if wanted else 1.0
        score = 0.4 + 0.6 * frac
        if frac < 1:
            notes.append(f"{len(wanted) - answered} step(s) left blank")
    elif practical.lab_type == "circuit":
        src = files.get("circuit.sim", "")
        if sum(1 for line in src.splitlines() if line.strip().startswith("#")) >= 2:
            score += 0.2
        else:
            notes.append("design is not commented")
    else:
        if result.cell_outputs and all(c.error is None for c in result.cell_outputs):
            score += 0.2
        else:
            notes.append("some cells fail to run")
    return max(0.0, min(1.0, score)), notes


class RubricGrader:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    def _apply_guardrails(self, practical: PracticalRecord, raw: dict[str, tuple[float, str]], pass_ratio: float) -> list[RubricScore]:
        out = []
        for crit in practical.rubric:
            score, feedback = raw.get(crit.id, (0.0, "Not assessed."))
            score = max(0.0, min(float(crit.max_points), float(score)))
            if crit.id in CORRECTNESS_IDS:
                score = min(score, crit.max_points * pass_ratio)  # correctness can't exceed test evidence
            out.append(RubricScore(criterion_id=crit.id, name=crit.name, score=_half(score),
                                   max_points=crit.max_points, feedback=feedback))
        return out

    @staticmethod
    def _scale_total(practical: PracticalRecord, breakdown: list[RubricScore]) -> float:
        rubric_max = sum(c.max_points for c in practical.rubric) or 1
        return round(sum(b.score for b in breakdown) / rubric_max * practical.max_score, 1)

    async def grade(self, practical: PracticalRecord, files: dict[str, str], result: ExecutionResult) -> GradeResult:
        pass_ratio = result.tests_passed / result.tests_total if result.tests_total else 0.0
        tests_text = "\n".join(
            f"- {t.name}{' [hidden]' if t.hidden else ''}: {'PASS' if t.passed else 'FAIL — ' + (t.message or '')}"
            for t in result.tests
        )
        files_text = "\n\n".join(f"### {n}\n{src[:15_000]}" for n, src in files.items())
        prompt = (
            f"LAB: {practical.title}\nBRIEF:\n{practical.description[:3000]}\n\n"
            f"RUBRIC (JSON):\n{json.dumps([c.model_dump() for c in practical.rubric])}\n\n"
            f"TEST RESULTS: {result.tests_passed}/{result.tests_total} passed\n{tests_text}\n\n"
            f"STUDENT FILES:\n{files_text}"
        )
        out = await self.ai.gemini_json(system=prompts.RUBRIC_GRADER, prompt=prompt, schema=_GradeOut, temperature=0.2)
        if out is not None and out.criteria:
            raw = {c.criterion_id: (c.score, c.feedback) for c in out.criteria}
            breakdown = self._apply_guardrails(practical, raw, pass_ratio)
            return GradeResult(breakdown=breakdown, total=self._scale_total(practical, breakdown),
                               summary=out.summary, model=self.ai.gemini_model)
        return self._fallback(practical, files, result, pass_ratio)

    def _fallback(self, practical: PracticalRecord, files: dict[str, str], result: ExecutionResult, pass_ratio: float) -> GradeResult:
        quality, notes = _quality_signals(practical, files, result)
        hidden = [t for t in result.tests if t.hidden]
        hidden_ratio = (sum(t.passed for t in hidden) / len(hidden)) if hidden else pass_ratio
        failing = [t.name for t in result.tests if not t.passed]
        raw: dict[str, tuple[float, str]] = {}
        for crit in practical.rubric:
            if crit.id in CORRECTNESS_IDS:
                frac = pass_ratio
                fb = ("All tests pass." if not failing else f"Failing: {', '.join(failing[:3])}.")
            elif crit.id in ("edge_cases", "visited"):
                frac = hidden_ratio
                fb = "Hidden edge-case tests pass." if hidden_ratio == 1 else "Some hidden edge-case tests fail."
            elif crit.id in ("efficiency",):
                frac = 1.0 if pass_ratio == 1 else 0.5
                fb = "No obvious inefficiencies detected." if frac == 1 else "Verify complexity once correctness issues are fixed."
            else:
                frac = quality
                fb = "Readable and well organised." if not notes else "Consider: " + ", ".join(notes) + "."
            raw[crit.id] = (crit.max_points * frac, fb)
        breakdown = self._apply_guardrails(practical, raw, pass_ratio)
        total = self._scale_total(practical, breakdown)
        summary = (
            f"Automated evaluation: {result.tests_passed}/{result.tests_total} tests passed. "
            + ("Great job — everything works." if not failing else f"Focus next on {failing[0]}.")
            + (" Code quality notes: " + ", ".join(notes) + "." if notes else "")
        )
        return GradeResult(breakdown=breakdown, total=total, summary=summary, model="rules")
