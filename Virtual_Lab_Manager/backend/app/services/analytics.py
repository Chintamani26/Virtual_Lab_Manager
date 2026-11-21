"""Department analytics powering the HOD dashboard, compliance report and conversational Q&A."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.db.base import Repository
from app.models import (
    CourseRecord,
    Department,
    ExecutionLogRecord,
    HintLogRecord,
    PracticalRecord,
    SubmissionRecord,
    UserRecord,
    utcnow,
)

IST = ZoneInfo("Asia/Kolkata")
AT_RISK_COMPLETION = 60.0
AT_RISK_SCORE = 50.0


@dataclass
class DeptData:
    department: Department
    courses: list[CourseRecord]
    faculty: dict[str, UserRecord]
    students: dict[str, UserRecord]
    enrollments: dict[str, list[str]]
    practicals: list[PracticalRecord]  # published only
    submissions: list[SubmissionRecord]
    executions: list[ExecutionLogRecord]
    hints: list[HintLogRecord]

    @property
    def course_by_id(self) -> dict[str, CourseRecord]:
        return {c.id: c for c in self.courses}


async def load_department(repo: Repository, department_id: str) -> DeptData:
    dept = await repo.get_department(department_id)
    if dept is None:
        raise LookupError("department not found")
    courses = await repo.list_courses(department_id=department_id)
    course_ids = [c.id for c in courses]
    practicals = await repo.list_practicals(course_ids, published_only=True)
    pids = [p.id for p in practicals]
    return DeptData(
        department=dept,
        courses=courses,
        faculty={u.id: u for u in await repo.list_users(department_id, "faculty")},
        students={u.id: u for u in await repo.list_users(department_id, "student")},
        enrollments=await repo.list_enrollments(course_ids),
        practicals=practicals,
        submissions=await repo.list_submissions(practical_ids=pids) if pids else [],
        executions=await repo.list_execution_logs(pids) if pids else [],
        hints=await repo.list_hint_logs(practical_ids=pids) if pids else [],
    )


def _pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 1) if xs else None


def best_scores(subs: list[SubmissionRecord]) -> dict[tuple[str, str], SubmissionRecord]:
    """(practical_id, student_id) -> best submission by final score."""
    best: dict[tuple[str, str], SubmissionRecord] = {}
    for s in subs:
        key = (s.practical_id, s.student_id)
        cur = best.get(key)
        if cur is None or (s.final_score or 0) > (cur.final_score or 0):
            best[key] = s
    return best


def practical_stats(d: DeptData) -> list[dict]:
    best = best_scores(d.submissions)
    courses = d.course_by_id
    rows = []
    for p in d.practicals:
        enrolled = d.enrollments.get(p.course_id, [])
        subs = [best[(p.id, sid)] for sid in enrolled if (p.id, sid) in best]
        scores = [100.0 * s.final_score / s.max_score for s in subs if s.final_score is not None]
        c = courses[p.course_id]
        rows.append({
            "practical_id": p.id, "practical_title": p.title, "course_id": c.id, "course_code": c.code,
            "course_title": c.title, "lab_type": p.lab_type, "due_at": p.due_at,
            "faculty_name": d.faculty[c.faculty_id].full_name if c.faculty_id in d.faculty else None,
            "enrolled": len(enrolled), "submitted": len(subs),
            "completion_rate": _pct(len(subs), len(enrolled)), "avg_score_pct": _mean(scores),
        })
    return rows


def student_risk(d: DeptData, now: datetime) -> list[dict]:
    best = best_scores(d.submissions)
    out = []
    for sid, stu in d.students.items():
        assigned = [
            p for p in d.practicals
            if sid in d.enrollments.get(p.course_id, []) and (p.due_at is None or p.due_at <= now)
        ] or [p for p in d.practicals if sid in d.enrollments.get(p.course_id, [])]
        if not assigned:
            continue
        done = [best[(p.id, sid)] for p in assigned if (p.id, sid) in best]
        scores = [100.0 * s.final_score / s.max_score for s in done if s.final_score is not None]
        completion = _pct(len(done), len(assigned))
        avg = _mean(scores)
        out.append({
            "student_id": sid, "student_name": stu.full_name, "roll_number": stu.roll_number,
            "completion_rate": completion, "avg_score_pct": avg,
            "at_risk": completion < AT_RISK_COMPLETION or (avg is not None and avg < AT_RISK_SCORE),
            "courses": sorted({c.code for c in d.courses if sid in d.enrollments.get(c.id, [])}),
        })
    return sorted(out, key=lambda r: (r["completion_rate"], r["avg_score_pct"] or 0))


def bottlenecks(d: DeptData, limit: int = 8) -> list[dict]:
    attempts: Counter = Counter()
    fails: Counter = Counter()
    for e in d.executions:
        if e.mode != "test":
            continue
        for t in e.test_results:
            attempts[(e.practical_id, t.name)] += 1
            if not t.passed:
                fails[(e.practical_id, t.name)] += 1
    hint_counts = Counter((h.practical_id, h.focus_test) for h in d.hints)
    by_id = {p.id: p for p in d.practicals}
    courses = d.course_by_id
    rows = []
    for key, n in attempts.items():
        if n < 3 or fails[key] == 0:
            continue
        p = by_id[key[0]]
        rows.append({
            "practical_id": p.id, "practical_title": p.title, "course_code": courses[p.course_id].code,
            "test_name": key[1], "fail_count": fails[key], "attempts": n,
            "fail_rate": _pct(fails[key], n), "hint_requests": hint_counts.get(key, 0),
        })
    rows.sort(key=lambda r: (r["fail_count"] * r["fail_rate"], r["hint_requests"]), reverse=True)
    return rows[:limit]


def overview(d: DeptData, now: datetime | None = None) -> dict:
    now = now or utcnow()
    pstats = practical_stats(d)
    risk = student_risk(d, now)
    best = best_scores(d.submissions)

    courses_rows = []
    for c in d.courses:
        cps = [r for r in pstats if r["course_id"] == c.id]
        enrolled = len(d.enrollments.get(c.id, []))
        scores = [r["avg_score_pct"] for r in cps if r["avg_score_pct"] is not None]
        courses_rows.append({
            "id": c.id, "code": c.code, "title": c.title, "semester": c.semester, "faculty_id": c.faculty_id,
            "faculty_name": d.faculty[c.faculty_id].full_name if c.faculty_id in d.faculty else None,
            "enrolled": enrolled, "practicals": len(cps), "submissions": sum(r["submitted"] for r in cps),
            "completion_rate": _pct(sum(r["submitted"] for r in cps), sum(r["enrolled"] for r in cps)),
            "avg_score_pct": _mean(scores),
        })

    all_scores = [100.0 * s.final_score / s.max_score for s in best.values() if s.final_score is not None]
    buckets = Counter(min(4, int(x // 20)) for x in all_scores)
    labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]

    today = now.astimezone(IST).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    ex_c = Counter(e.created_at.astimezone(IST).date() for e in d.executions)
    sub_c = Counter(s.submitted_at.astimezone(IST).date() for s in d.submissions)
    hint_c = Counter(h.created_at.astimezone(IST).date() for h in d.hints)

    return {
        "department": {
            "id": d.department.id, "name": d.department.name, "code": d.department.code,
            "institution_name": d.department.institution_name,
        },
        "kpis": {
            "students": len(d.students), "faculty": len(d.faculty), "courses": len(d.courses),
            "practicals": len(d.practicals), "submissions": len(d.submissions),
            "completion_rate": _pct(sum(r["submitted"] for r in pstats), sum(r["enrolled"] for r in pstats)),
            "avg_score_pct": _mean(all_scores),
            "at_risk_students": sum(1 for r in risk if r["at_risk"]),
            "ai_hints_served": len(d.hints),
            "integrity_flags": sum(1 for s in d.submissions if s.integrity and s.integrity.risk_level != "low"),
        },
        "courses": courses_rows,
        "bottlenecks": bottlenecks(d),
        "at_risk": [
            {k: r[k] for k in ("student_id", "student_name", "roll_number", "completion_rate", "avg_score_pct")}
            for r in risk if r["at_risk"]
        ][:10],
        "activity": [
            {"date": day.isoformat(), "executions": ex_c.get(day, 0), "submissions": sub_c.get(day, 0),
             "hints": hint_c.get(day, 0)}
            for day in days
        ],
        "score_distribution": [{"bucket": labels[i], "count": buckets.get(i, 0)} for i in range(5)],
    }


def compliance_rows(d: DeptData, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    rows = []
    for r in practical_stats(d):
        due = r["due_at"]
        if due is not None and due < now:
            status = "compliant" if r["completion_rate"] >= 85 else ("at_risk" if r["completion_rate"] >= 60 else "non_compliant")
        else:  # still open: judge by trajectory
            status = "compliant" if r["completion_rate"] >= 60 else "at_risk"
        rows.append({
            "course_code": r["course_code"], "course_title": r["course_title"], "faculty_name": r["faculty_name"],
            "practical_title": r["practical_title"], "due_at": due.isoformat() if due else None,
            "enrolled": r["enrolled"], "submitted": r["submitted"], "completion_rate": r["completion_rate"],
            "avg_score_pct": r["avg_score_pct"], "status": status,
        })
    for c in d.courses:
        if not any(p.course_id == c.id for p in d.practicals):
            rows.append({
                "course_code": c.code, "course_title": c.title,
                "faculty_name": d.faculty[c.faculty_id].full_name if c.faculty_id in d.faculty else None,
                "practical_title": "(no practicals published)", "due_at": None,
                "enrolled": len(d.enrollments.get(c.id, [])), "submitted": 0, "completion_rate": 0.0,
                "avg_score_pct": None, "status": "non_compliant",
            })
    return rows


def llm_snapshot(d: DeptData, now: datetime | None = None) -> dict:
    """Compact, PII-light context for the HOD analyst (names of students are needed for at-risk questions)."""
    now = now or utcnow()
    ov = overview(d, now)
    risk = student_risk(d, now)
    return {
        "as_of": now.astimezone(IST).strftime("%Y-%m-%d %H:%M IST"),
        "department": ov["department"]["name"],
        "kpis": ov["kpis"],
        "courses": [{k: v for k, v in c.items() if k not in ("id", "faculty_id")} for c in ov["courses"]],
        "practicals": [
            {**{k: v for k, v in r.items() if k not in ("practical_id", "course_id")},
             "due_at": r["due_at"].astimezone(IST).strftime("%Y-%m-%d") if r["due_at"] else None}
            for r in practical_stats(d)
        ],
        "bottleneck_tests": ov["bottlenecks"],
        "students": [
            {k: r[k] for k in ("student_name", "roll_number", "completion_rate", "avg_score_pct", "at_risk", "courses")}
            for r in risk
        ],
        "faculty": [
            {"name": f.full_name, "courses": [c.code for c in d.courses if c.faculty_id == f.id]}
            for f in d.faculty.values()
        ],
        "integrity_flags": integrity_flags(d),
        "activity_last_14_days": ov["activity"],
        "notes": "completion_rate and avg_score_pct are percentages; at_risk = completion < 60% or avg < 50%. "
                 "integrity_flags are indicators for faculty review, not proof of misconduct.",
    }


def faculty_practical_stats(
    practicals: list[PracticalRecord], enrollments: dict[str, list[str]], subs: list[SubmissionRecord]
) -> dict[str, dict]:
    by_p: dict[str, list[SubmissionRecord]] = defaultdict(list)
    for s in subs:
        by_p[s.practical_id].append(s)
    out = {}
    for p in practicals:
        best = best_scores(by_p.get(p.id, []))
        scores = [s.final_score for s in best.values() if s.final_score is not None]
        full = [s for s in best.values() if s.tests_total and s.tests_passed == s.tests_total]
        out[p.id] = {
            "enrolled": len(enrollments.get(p.course_id, [])),
            "submitted": len(best),
            "avg_score": _mean(scores),
            "pass_rate": _pct(len(full), len(best)) if best else None,
        }
    return out


def integrity_flags(d: DeptData, limit: int = 15) -> list[dict]:
    """Submissions with medium/high integrity risk (highest first)."""
    by_id = {p.id: p for p in d.practicals}
    courses = d.course_by_id
    rows = []
    for s in d.submissions:
        if not s.integrity or s.integrity.risk_level == "low" or s.practical_id not in by_id:
            continue
        p = by_id[s.practical_id]
        stu = d.students.get(s.student_id)
        rows.append({
            "student_name": stu.full_name if stu else "unknown", "roll_number": stu.roll_number if stu else None,
            "course_code": courses[p.course_id].code, "practical_title": p.title,
            "risk_level": s.integrity.risk_level, "risk_score": s.integrity.risk_score,
            "ai_likelihood": s.integrity.ai_likelihood,
            "top_signals": [x.label for x in s.integrity.signals[:3]],
        })
    rows.sort(key=lambda r: r["risk_score"], reverse=True)
    return rows[:limit]
