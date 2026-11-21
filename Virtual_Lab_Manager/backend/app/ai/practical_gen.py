"""Faculty: create a complete coding practical from a topic, verified in the sandbox before anyone sees it.

    topic -> Gemini (brief in lab-manual layout, starter, reference solution, tests, rubric, viva questions)
          -> structural checks (code parses, test names, rubric scaled to 10)
          -> sandbox: run the tests on the reference solution (must pass) and on the starter (must fail)
          -> one repair round with the failures if fewer than 3 tests survive
          -> draft for the faculty member to review; nothing is saved or published here

The reference solution is returned for the faculty member's Validate box only. It is never stored with the
practical, so it can't reach students or the tutor.
"""

from __future__ import annotations

import ast
import re

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.ai.testgen import _GenTest, validate_generated
from app.execution.base import ExecutionRequest
from app.execution.service import ExecutionInputError, ExecutionService
from app.models import CourseRecord, RubricCriterion, TestCaseSpec
from app.schemas import GeneratedPracticalOut, GeneratePracticalRequest, PracticalVerification

MIN_TESTS = 3
MAX_SCORE = 10.0


class AIUnavailable(Exception):
    """Gemini isn't configured, or didn't return a usable result."""


class _Test(BaseModel):
    name: str
    description: str
    hidden: bool
    code: str


class _Criterion(BaseModel):
    name: str
    description: str
    max_points: float


class _Practical(BaseModel):
    title: str
    aim: str
    objectives: list[str]
    theory: str
    problem_statement: str
    io_examples: str
    constraints: list[str]
    starter_code: str
    reference_solution: str
    tests: list[_Test]
    rubric: list[_Criterion]
    viva_questions: list[str]


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
        return bool(code.strip())
    except SyntaxError:
        return False


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "criterion"


def scale_rubric(items: list[_Criterion], total: float = MAX_SCORE) -> list[RubricCriterion]:
    """Rubric points rescaled to `total` in 0.5 steps (rounding drift goes to the largest criterion)."""
    items = [c for c in items if c.name.strip() and c.max_points > 0][:6]
    if not items:
        return [RubricCriterion(id="correctness", name="Correctness", description="Passes the tests.", max_points=7),
                RubricCriterion(id="code_quality", name="Code quality", description="Readable, well-named code.",
                                max_points=3)]
    raw = sum(c.max_points for c in items)
    pts = [max(0.5, round(c.max_points / raw * total * 2) / 2) for c in items]
    pts[pts.index(max(pts))] += total - sum(pts)
    seen: set[str] = set()
    out = []
    for c, p in zip(items, pts):
        cid = _slug(c.name)
        while cid in seen:
            cid += "_2"
        seen.add(cid)
        out.append(RubricCriterion(id=cid, name=c.name.strip()[:120], description=c.description.strip()[:500],
                                   max_points=p))
    return out


def brief_markdown(g: _Practical) -> str:
    def bullets(xs: list[str]) -> str:
        return "\n".join(f"- {x.strip()}" for x in xs if x.strip())

    parts = [f"## {g.title.strip()[:120]}", f"### Aim\n{g.aim.strip()}"]
    if g.objectives:
        parts.append(f"### Objectives\n{bullets(g.objectives[:6])}")
    parts.append(f"### Theory\n{g.theory.strip()}")
    parts.append(f"### Problem statement\n{g.problem_statement.strip()}")
    if g.io_examples.strip():
        parts.append(f"### Examples\n{g.io_examples.strip()}")
    if g.constraints:
        parts.append(f"### Constraints\n{bullets(g.constraints[:6])}")
    if g.viva_questions:
        parts.append("### Viva questions\n" + "\n".join(f"{i}. {q.strip()}" for i, q in enumerate(g.viva_questions[:6], 1)))
    return "\n\n".join(parts)[:20_000]


class PracticalGenerator:
    def __init__(self, ai: AIClient, execution: ExecutionService) -> None:
        self.ai = ai
        self.execution = execution

    async def generate(self, req: GeneratePracticalRequest, course: CourseRecord | None) -> GeneratedPracticalOut:
        if not self.ai.enabled:
            raise AIUnavailable("AI generation needs Gemini (GEMINI_API_KEY). Start from the template instead.")
        request = (
            f"Topic: {req.topic}\nDifficulty: {req.difficulty}\nTime available: {req.duration_minutes} minutes\n"
            + (f"Course: {course.code} {course.title} (semester {course.semester})\n" if course else "")
            + (f"Faculty notes: {req.notes}\n" if req.notes.strip() else "")
        )
        prompt = f"<<request>>\n{request}<</request>>"
        best: tuple[_Practical, list[TestCaseSpec], PracticalVerification] | None = None
        feedback = ""
        for attempt in (1, 2):
            g = await self.ai.gemini_json(system=prompts.PRACTICAL_GENERATOR, prompt=prompt + feedback,
                                          schema=_Practical, temperature=0.5, max_tokens=8192, timeout_s=90)
            if g is None or not _parses(g.reference_solution) or not _parses(g.starter_code):
                feedback = ("\n\nYOUR PREVIOUS ANSWER WAS UNUSABLE (missing or invalid Python in starter_code or "
                            "reference_solution). Return a complete, valid practical.")
                continue
            tests = validate_generated("coding", [_GenTest(name=t.name, description=t.description, hidden=t.hidden,
                                                           code=t.code, inputs_json="", expected_json="")
                                                  for t in g.tests])
            kept, verification, failures, ref_failed = await self._verify(g, tests)
            verification.attempts = attempt
            if best is None or len(kept) >= len(best[1]):
                best = (g, kept, verification)
            # a test failing on the reference means the test or the reference is wrong: repair once
            if len(kept) >= MIN_TESTS and not ref_failed:
                break
            feedback = ("\n\nYOUR PREVIOUS PRACTICAL FAILED VERIFICATION. These tests failed when run against your "
                        "own reference_solution (or passed on the empty starter):\n" + failures[:3000]
                        + "\nReturn a corrected complete practical whose reference_solution passes every test.")
        if best is None:
            raise AIUnavailable("Gemini didn't return a usable practical. Try again, or rephrase the topic.")
        g, kept, verification = best
        if len(kept) < MIN_TESTS:
            verification.note = (f"Only {len(kept)} generated test(s) passed on the reference solution. Review the "
                                 "tests before publishing.")
        return GeneratedPracticalOut(
            title=g.title.strip()[:200], description=brief_markdown(g),
            starter_files={"main.py": g.starter_code.strip() + "\n"}, test_cases=kept,
            rubric=scale_rubric(g.rubric), max_score=MAX_SCORE,
            viva_questions=[q.strip() for q in g.viva_questions if q.strip()][:6],
            reference_files={"main.py": g.reference_solution.strip() + "\n"},
            verification=verification, model=self.ai.gemini_model, source="gemini",
        )

    async def _run(self, code: str, tests: list[TestCaseSpec]):
        try:
            return await self.execution.execute(ExecutionRequest(lab_type="coding", files={"main.py": code},
                                                                 mode="test", tests=tests))
        except ExecutionInputError:
            return None

    async def _verify(self, g: _Practical, tests: list[TestCaseSpec]):
        """Keep tests that pass on the reference and fail on the starter.
        Returns (kept, verification, failures for the repair prompt, number of tests failing on the reference)."""
        if not tests:
            return [], PracticalVerification(verified=False, tests_total=0, reference_passed=0, starter_failed=0,
                                             note="Gemini returned no valid tests."), "no valid tests", 1
        ref = await self._run(g.reference_solution, tests)
        starter = await self._run(g.starter_code, tests)
        ref_ok = {t.name for t in ref.tests if t.passed} if ref else set()
        starter_ok = {t.name for t in starter.tests if t.passed} if starter else set()
        kept = [t for t in tests if t.name in ref_ok and t.name not in starter_ok]
        if len(kept) < MIN_TESTS:  # a test that also passes on the skeleton is weak, but better than nothing
            kept = [t for t in tests if t.name in ref_ok]
        if kept and not any(t.hidden for t in kept) and len(kept) >= 4:
            kept[-1] = kept[-1].model_copy(update={"hidden": True})
        if kept and all(t.hidden for t in kept):
            kept[0] = kept[0].model_copy(update={"hidden": False})
        failures = "\n".join(
            f"- {t.name}: {t.message or 'failed'}" for t in (ref.tests if ref else []) if not t.passed
        ) + "".join(f"\n- {n}: passes on the starter code (checks nothing)" for n in sorted(starter_ok & ref_ok))
        if ref is None or not ref.tests:
            failures = "the reference solution could not be run: " + ((ref.stderr[-800:] if ref else "") or "error")
        kept_names = {t.name for t in kept}
        verification = PracticalVerification(
            verified=bool(kept) and all(n not in starter_ok for n in kept_names),
            tests_total=len(kept), reference_passed=len(kept_names & ref_ok),
            starter_failed=len(kept_names - starter_ok), dropped=[t.name for t in tests if t.name not in kept_names],
        )
        return kept, verification, failures, len(tests) - len(ref_ok & {t.name for t in tests})
