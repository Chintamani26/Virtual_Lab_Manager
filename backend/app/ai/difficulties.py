"""Learning Difficulty Analyzer: the concepts students struggle with most, per course.

Evidence (app/services/insights.py) -> Gemini names the concept, explains it and recommends a teaching action
-> the reply is checked against the evidence: unknown courses and test names are dropped, example questions must
be verbatim student questions, and every number (students affected, fail rate, hints) is recomputed here.
Without Gemini the same evidence gives a rule-based ranking. Results are cached for CACHE_S per scope.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.models import utcnow
from app.schemas import CourseDifficultiesOut, DifficultyOut, LearningDifficultiesOut
from app.services.insights import CourseEvidence, TestEvidence

CACHE_S = 15 * 60
PER_COURSE = 3


class _Difficulty(BaseModel):
    course_code: str
    concept: str
    explanation: str
    related_tests: list[str]
    example_questions: list[str]
    recommended_action: str


class _Out(BaseModel):
    difficulties: list[_Difficulty]


def _humanise(test: str) -> str:
    return test.removeprefix("test_").replace("_", " ").strip().capitalize() or test


def _out(concept: str, explanation: str, action: str, related: list[TestEvidence], questions: list[str]) -> DifficultyOut:
    lead = max(related, key=lambda ev: len(ev.students_failed))
    affected = set().union(*(ev.students_failed for ev in related))
    attempted = set().union(*(ev.students_attempted for ev in related))
    return DifficultyOut(
        concept=concept.strip()[:80], explanation=explanation.strip()[:500], recommended_action=action.strip()[:500],
        practical_id=lead.practical_id, practical_title=lead.practical_title, tests=[ev.test for ev in related],
        students_affected=len(affected), students_attempted=len(attempted), fail_rate=lead.fail_rate,
        hint_requests=sum(ev.hint_requests for ev in related), example_questions=questions[:3],
    )


def rule_based(ev: CourseEvidence) -> list[DifficultyOut]:
    out = []
    for t in ev.tests[:PER_COURSE]:
        concept = t.known_concept or t.description.rstrip(".") or _humanise(t.test)
        explanation = (f"{len(t.students_failed)} of {len(t.students_attempted)} students who ran the tests failed "
                       f"`{t.test}` at least once ({t.fail_rate}% of runs).")
        action = f"Revisit \u201c{concept}\u201d with a worked example and a short in-class exercise before the next lab."
        if t.hint_requests:
            action += f" Students asked for {t.hint_requests} hint{'s' if t.hint_requests != 1 else ''} on it."
        out.append(_out(concept, explanation, action, [t], t.questions))
    return out


class LearningDifficultyAnalyzer:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai
        self._cache: dict[str, tuple[float, LearningDifficultiesOut]] = {}

    async def analyze(self, scope: str, evidence: list[CourseEvidence], *, refresh: bool = False) -> LearningDifficultiesOut:
        hit = self._cache.get(scope)
        if hit and not refresh and time.monotonic() - hit[0] < CACHE_S:
            return hit[1].model_copy(update={"cached": True})
        result = await self._analyze(evidence)
        self._cache[scope] = (time.monotonic(), result)
        return result

    async def _analyze(self, evidence: list[CourseEvidence]) -> LearningDifficultiesOut:
        now: datetime = utcnow()
        with_data = [ev for ev in evidence if ev.tests]
        ai = await self._ask_model(with_data) if with_data and self.ai.enabled else None
        courses = []
        for ev in evidence:
            items = ai.get(ev.course.code) if ai is not None else None
            courses.append(CourseDifficultiesOut(
                course_id=ev.course.id, course_code=ev.course.code, course_title=ev.course.title,
                faculty_name=ev.faculty_name, difficulties=items if items else rule_based(ev),
            ))
        used_ai = ai is not None and any(ai.values())
        return LearningDifficultiesOut(generated_at=now, courses=courses,
                                       model=self.ai.gemini_model if used_ai else "rules",
                                       source="gemini" if used_ai else "fallback")

    async def _ask_model(self, evidence: list[CourseEvidence]) -> dict[str, list[DifficultyOut]] | None:
        blocks = []
        for ev in evidence:
            data = {"course": f"{ev.course.code} {ev.course.title}", "failing_tests": [t.as_prompt() for t in ev.tests],
                    "concept_checks": dict(ev.concept_checks)}
            qs = "\n".join(f"- {q}" for q in ev.questions) or "(none)"
            blocks.append(f"COURSE {ev.course.code} EVIDENCE:\n{json.dumps(data, ensure_ascii=False)}\n"
                          f"<<student_questions {ev.course.code}>>\n{qs}\n<</student_questions {ev.course.code}>>")
        out = await self.ai.gemini_json(system=prompts.LEARNING_DIFFICULTIES, prompt="\n\n".join(blocks), schema=_Out,
                                        temperature=0.2, max_tokens=4096, timeout_s=60)
        if out is None:
            return None
        by_code = {ev.course.code: ev for ev in evidence}
        result: dict[str, list[DifficultyOut]] = {code: [] for code in by_code}
        for item in out.difficulties:
            ev = by_code.get(item.course_code.strip().split()[0] if item.course_code.strip() else "")
            if ev is None or len(result[ev.course.code]) >= PER_COURSE:
                continue
            tests = {t.test: t for t in ev.tests}
            related = [tests[n] for n in dict.fromkeys(item.related_tests) if n in tests]
            if not related or not item.concept.strip():
                continue
            known = {q.lower(): q for q in ev.questions}
            quotes = [known[q.strip().lower()] for q in item.example_questions if q.strip().lower() in known]
            result[ev.course.code].append(_out(item.concept, item.explanation, item.recommended_action, related, quotes))
        for items in result.values():
            items.sort(key=lambda d: d.students_affected, reverse=True)
        return result
