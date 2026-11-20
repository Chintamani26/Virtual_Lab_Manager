"""Deterministic evidence for the AI department-intelligence features.

The numbers shown to the HOD (students affected, fail rates, week-over-week changes) are computed here from the
data. Gemini only names, explains and prioritises (app/ai/difficulties.py, app/ai/briefing.py).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.ai.tutor import CURATED
from app.ai.tutor_chat import ACTION_LABELS
from app.models import CourseRecord, TutorThreadRecord
from app.services.analytics import IST, DeptData, bottlenecks, practical_stats, student_risk

MAX_CANDIDATES = 6       # tests per course sent to the model
MAX_QUESTIONS = 30       # student questions per course sent to the model
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_GUARDED = {"injection", "restricted"}


@dataclass
class TestEvidence:
    practical_id: str
    practical_title: str
    test: str
    description: str
    known_concept: str | None
    attempts: int = 0
    fails: int = 0
    students_failed: set[str] = field(default_factory=set)
    students_attempted: set[str] = field(default_factory=set)
    hint_requests: int = 0
    questions: list[str] = field(default_factory=list)  # anonymised questions asked with hints on this test

    @property
    def fail_rate(self) -> float:
        return round(100.0 * self.fails / self.attempts, 1) if self.attempts else 0.0

    def as_prompt(self) -> dict:
        return {"practical": self.practical_title, "test": self.test, "checks": self.description,
                "known_concept": self.known_concept, "students_failed": len(self.students_failed),
                "students_attempted": len(self.students_attempted), "fail_rate_pct": self.fail_rate,
                "hint_requests": self.hint_requests}


@dataclass
class CourseEvidence:
    course: CourseRecord
    faculty_name: str | None
    tests: list[TestEvidence]
    questions: list[str]
    concept_checks: Counter


def anonymise(text: str, names: list[str]) -> str:
    text = _EMAIL.sub("[student]", text)
    for n in names:
        if n:
            text = re.sub(rf"\b{re.escape(n)}\b", "[student]", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()[:200]


def _student_questions(threads: list[TutorThreadRecord]) -> list[tuple[datetime, str, str]]:
    """(time, practical_id, text) of questions students typed to the tutor; quick-action labels, guarded
    messages and concept-check answers are left out."""
    labels = set(ACTION_LABELS.values())
    out = []
    for t in threads:
        prev = None
        for m in t.messages:
            answering = prev is not None and prev.role == "tutor" and prev.expects_answer
            if (m.role == "student" and m.action in ("chat", "explain_concept", "next_hint") and not answering
                    and m.content not in labels and not (_GUARDED & set(m.flags)) and len(m.content) >= 8):
                out.append((m.created_at, t.practical_id, m.content))
            prev = m
    return out


def difficulty_evidence(d: DeptData, threads: list[TutorThreadRecord],
                        course_ids: set[str] | None = None) -> list[CourseEvidence]:
    practicals = {p.id: p for p in d.practicals if course_ids is None or p.course_id in course_ids}
    tests: dict[tuple[str, str], TestEvidence] = {}
    for p in practicals.values():
        for spec in p.test_cases:
            known = CURATED[spec.name][0][0] if spec.name in CURATED else None
            tests[(p.id, spec.name)] = TestEvidence(p.id, p.title, spec.name, spec.description, known)
    for e in d.executions:
        if e.mode != "test" or e.practical_id not in practicals:
            continue
        for r in e.test_results:
            ev = tests.get((e.practical_id, r.name))
            if ev is None:
                continue
            ev.attempts += 1
            ev.students_attempted.add(e.student_id)
            if not r.passed:
                ev.fails += 1
                ev.students_failed.add(e.student_id)
    for h in d.hints:
        if (ev := tests.get((h.practical_id, h.focus_test or ""))) is not None:
            ev.hint_requests += 1

    names = [n for u in d.students.values() for n in (u.full_name, *u.full_name.split(), u.roll_number or "")]
    questions: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for h in sorted(d.hints, key=lambda h: h.created_at, reverse=True):
        if h.question and h.practical_id in practicals:
            questions[practicals[h.practical_id].course_id].append((h.created_at, h.question))
            ev = tests.get((h.practical_id, h.focus_test or ""))
            q = anonymise(h.question, names)
            if ev is not None and q.lower() not in {x.lower() for x in ev.questions}:
                ev.questions.append(q)
    for at, pid, text in _student_questions(threads):
        if pid in practicals:
            questions[practicals[pid].course_id].append((at, text))
    checks: dict[str, Counter] = defaultdict(Counter)
    for t in threads:
        if t.practical_id in practicals:
            for m in t.messages:
                if m.role == "tutor" and m.understanding:
                    checks[practicals[t.practical_id].course_id][m.understanding] += 1

    out = []
    for c in d.courses:
        if course_ids is not None and c.id not in course_ids:
            continue
        cands = [ev for (pid, _), ev in tests.items()
                 if practicals[pid].course_id == c.id and ev.attempts >= 3 and ev.students_failed]
        cands.sort(key=lambda ev: (len(ev.students_failed) * ev.fail_rate, ev.hint_requests), reverse=True)
        seen: set[str] = set()
        qs = []
        for _, q in sorted(questions.get(c.id, []), reverse=True):
            q = anonymise(q, names)
            if q.lower() not in seen:
                seen.add(q.lower())
                qs.append(q)
        out.append(CourseEvidence(
            course=c, faculty_name=d.faculty[c.faculty_id].full_name if c.faculty_id in d.faculty else None,
            tests=cands[:MAX_CANDIDATES], questions=qs[:MAX_QUESTIONS], concept_checks=checks.get(c.id, Counter()),
        ))
    return out


# ---------------------------------------------------------------- weekly briefing
def _window(d: DeptData, start: datetime, end: datetime) -> dict:
    subs = [s for s in d.submissions if start <= s.submitted_at < end]
    runs = [e for e in d.executions if e.mode == "test" and start <= e.created_at < end]
    scores = [100.0 * s.final_score / s.max_score for s in subs if s.final_score is not None and s.max_score]
    return {
        "submissions": len(subs), "test_runs": len(runs),
        "hint_requests": sum(1 for h in d.hints if start <= h.created_at < end),
        "active_students": len({s.student_id for s in subs} | {e.student_id for e in runs}),
        "avg_score_pct": round(statistics.mean(scores), 1) if scores else None,
        "integrity_flags": sum(1 for s in subs if s.integrity and s.integrity.risk_level != "low"),
    }


def weekly_metrics(d: DeptData, now: datetime) -> dict:
    start = now - timedelta(days=7)
    courses = d.course_by_id
    pending: dict[str, dict] = {}
    for s in d.submissions:
        if s.status != "graded":
            continue
        p = next((x for x in d.practicals if x.id == s.practical_id), None)
        if p is None:
            continue
        c = courses[p.course_id]
        row = pending.setdefault(c.code, {
            "course": c.code, "faculty": d.faculty[c.faculty_id].full_name if c.faculty_id in d.faculty else "unassigned",
            "pending_reviews": 0, "oldest_days": 0,
        })
        row["pending_reviews"] += 1
        row["oldest_days"] = max(row["oldest_days"], (now - s.submitted_at).days)
    behind = []
    for r in practical_stats(d):
        due = r["due_at"]
        if due is None:
            continue
        overdue = due <= now and r["completion_rate"] < 60
        due_soon = now < due <= now + timedelta(days=7) and r["completion_rate"] < 50
        if overdue or due_soon:
            behind.append({"course": r["course_code"], "practical": r["practical_title"],
                           "faculty": r["faculty_name"] or "unassigned", "completion_pct": r["completion_rate"],
                           "due": due.astimezone(IST).strftime("%d %b"), "status": "overdue" if overdue else "due this week"})
    risk = [r for r in student_risk(d, now) if r["at_risk"]]
    return {
        "department": d.department.name,
        "period": f"{start.astimezone(IST):%d %b} – {now.astimezone(IST):%d %b %Y}",
        "students": len(d.students), "courses": len(d.courses), "practicals_published": len(d.practicals),
        "this_week": _window(d, start, now), "last_week": _window(d, start - timedelta(days=7), start),
        "pending_reviews": sorted(pending.values(), key=lambda r: -r["pending_reviews"]),
        "practicals_behind": sorted(behind, key=lambda r: r["completion_pct"])[:6],
        "at_risk_students": {"count": len(risk), "examples": [r["student_name"] for r in risk[:5]]},
        "unassigned_courses": [c.code for c in d.courses if c.faculty_id not in d.faculty],
        "top_bottlenecks": [{"course": b["course_code"], "practical": b["practical_title"], "test": b["test_name"],
                             "fail_rate_pct": b["fail_rate"], "hint_requests": b["hint_requests"]}
                            for b in bottlenecks(d, limit=3)],
    }
