"""Student & Faculty Intelligence — deterministic analytics (no AI).

Provides faculty-scoped and HOD-scoped functions for:
  - Student performance analytics (score distributions, rubric breakdowns, hint usage)
  - Faculty workload analytics (pending review, turnaround)
  - Learning difficulty heatmaps (test-level fail rates)
  - Course completion tracking (submitted / in-progress / overdue)
  - At-risk student identification (deterministic risk score)
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from app.models import (
    CourseRecord,
    ExecutionLogRecord,
    HintLogRecord,
    PracticalRecord,
    SubmissionRecord,
    UserRecord,
)
from app.services.analytics import DeptData, _mean, _pct, best_scores

# ---------------------------------------------------------------------------
# Risk thresholds (deterministic, no AI)
# ---------------------------------------------------------------------------
RISK_LOW_COMPLETION = 60.0   # < 60% completion → +40 pts
RISK_LOW_SCORE = 50.0        # avg < 50% → +25 pts
RISK_OVERDUE_MIN = 2         # ≥ 2 overdue → +20 pts
RISK_STAGNANT_SCORE = 40.0   # score < 40 on 2+ attempts → +15 pts

RISK_HIGH = 60
RISK_MED = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared helper: score distribution buckets
# ---------------------------------------------------------------------------
def _score_buckets(scores_pct: list[float]) -> list[dict]:
    labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    counts = Counter(min(4, int(x // 20)) for x in scores_pct)
    return [{"bucket": labels[i], "count": counts.get(i, 0)} for i in range(5)]


# ===========================================================================
# FACULTY-SCOPED INTELLIGENCE
# ===========================================================================

def faculty_student_performance(
    courses: list[CourseRecord],
    practicals: list[PracticalRecord],
    enrollments: dict[str, list[str]],  # course_id → [student_id]
    submissions: list[SubmissionRecord],
    hints: list[HintLogRecord],
    generated_at: datetime | None = None,
) -> dict:
    """Per-course, per-practical score distributions, rubric breakdowns, hint usage."""
    generated_at = generated_at or _utcnow()
    course_by_id = {c.id: c for c in courses}
    practical_by_id = {p.id: p for p in practicals}

    # Group submissions by practical
    subs_by_practical: dict[str, list[SubmissionRecord]] = defaultdict(list)
    for s in submissions:
        subs_by_practical[s.practical_id].append(s)

    # Hint counts by practical
    hints_by_practical: Counter = Counter(h.practical_id for h in hints)
    # Unique students who requested hints per practical
    hint_students: dict[str, set] = defaultdict(set)
    for h in hints:
        hint_students[h.practical_id].add(h.student_id)

    # Group practicals by course
    practicals_by_course: dict[str, list[PracticalRecord]] = defaultdict(list)
    for p in practicals:
        practicals_by_course[p.course_id].append(p)

    courses_out = []
    for c in courses:
        course_practicals = practicals_by_course.get(c.id, [])
        practical_rows = []
        for p in course_practicals:
            enrolled_ids = enrollments.get(p.course_id, [])
            best = best_scores(subs_by_practical.get(p.id, []))
            submitted_subs = [best[(p.id, sid)] for sid in enrolled_ids if (p.id, sid) in best]
            # Also include submissions from non-enrolled (edge case)
            submitted_subs = list(best.values()) if not submitted_subs else submitted_subs

            scores_pct = [
                100.0 * s.final_score / s.max_score
                for s in submitted_subs
                if s.final_score is not None and s.max_score
            ]
            pass_count = sum(
                1 for s in submitted_subs
                if s.tests_total and s.tests_passed == s.tests_total
            )

            # Rubric breakdown: avg score per criterion
            rubric_map: dict[str, dict] = {}
            for s in submitted_subs:
                for rb in s.rubric_breakdown:
                    if rb.criterion_id not in rubric_map:
                        rubric_map[rb.criterion_id] = {
                            "criterion_id": rb.criterion_id,
                            "criterion_name": rb.name,
                            "max_points": rb.max_points,
                            "scores": [],
                        }
                    rubric_map[rb.criterion_id]["scores"].append(rb.score)
            rubric_breakdown = []
            for crit in rubric_map.values():
                avg = _mean(crit["scores"]) or 0.0
                rubric_breakdown.append({
                    "criterion_id": crit["criterion_id"],
                    "criterion_name": crit["criterion_name"],
                    "avg_score": avg,
                    "max_points": crit["max_points"],
                    "avg_pct": round(100.0 * avg / crit["max_points"], 1) if crit["max_points"] else 0.0,
                })

            total_hints = hints_by_practical.get(p.id, 0)
            hint_student_count = len(hint_students.get(p.id, set()))

            practical_rows.append({
                "practical_id": p.id,
                "practical_title": p.title,
                "course_code": c.code,
                "lab_type": p.lab_type,
                "enrolled": len(enrolled_ids),
                "submitted": len(submitted_subs),
                "avg_score_pct": _mean(scores_pct),
                "pass_rate": _pct(pass_count, len(submitted_subs)) if submitted_subs else None,
                "score_distribution": _score_buckets(scores_pct),
                "rubric_breakdown": rubric_breakdown,
                "hint_usage": {
                    "total": total_hints,
                    "avg_per_student": round(total_hints / hint_student_count, 1) if hint_student_count else 0.0,
                },
            })

        courses_out.append({
            "course_id": c.id,
            "course_code": c.code,
            "course_title": c.title,
            "practicals": practical_rows,
        })

    return {"generated_at": generated_at.isoformat(), "courses": courses_out}


def faculty_workload(
    faculty_user_id: str,
    courses: list[CourseRecord],
    practicals: list[PracticalRecord],
    submissions: list[SubmissionRecord],
    now: datetime | None = None,
) -> dict:
    """Pending review count, oldest pending, reviewed count, avg turnaround, per-course breakdown."""
    now = now or _utcnow()
    week_ago = now - timedelta(days=7)
    course_by_id = {c.id: c for c in courses}
    practical_to_course: dict[str, str] = {p.id: p.course_id for p in practicals}

    pending: list[SubmissionRecord] = []
    reviewed_this_week: list[SubmissionRecord] = []
    turnaround_days: list[float] = []

    for s in submissions:
        if s.status == "graded":
            pending.append(s)
        elif s.status == "reviewed":
            if s.reviewed_at and s.reviewed_at >= week_ago:
                reviewed_this_week.append(s)
            if s.reviewed_at and s.submitted_at:
                td = (s.reviewed_at - s.submitted_at).total_seconds() / 86400
                turnaround_days.append(max(0.0, td))

    oldest_days: float | None = None
    if pending:
        oldest = min(s.submitted_at for s in pending)
        oldest_days = round((now - oldest).total_seconds() / 86400, 1)

    # Per-course breakdown
    by_course: dict[str, dict] = {}
    for c in courses:
        by_course[c.id] = {"course_code": c.code, "course_title": c.title, "pending": 0, "reviewed": 0}

    for s in submissions:
        cid = practical_to_course.get(s.practical_id)
        if cid and cid in by_course:
            if s.status == "graded":
                by_course[cid]["pending"] += 1
            else:
                by_course[cid]["reviewed"] += 1

    return {
        "pending_review": len(pending),
        "oldest_pending_days": oldest_days,
        "reviewed_this_week": len(reviewed_this_week),
        "avg_turnaround_days": _mean(turnaround_days),
        "by_course": list(by_course.values()),
    }


def faculty_completion_tracking(
    courses: list[CourseRecord],
    practicals: list[PracticalRecord],
    enrollments: dict[str, list[str]],
    submissions: list[SubmissionRecord],
    now: datetime | None = None,
) -> list[dict]:
    """Per-practical: enrolled, submitted, overdue, completion_pct, pacing_gap."""
    now = now or _utcnow()
    course_by_id = {c.id: c for c in courses}

    submitted_set: set[tuple[str, str]] = set()
    for s in submissions:
        submitted_set.add((s.practical_id, s.student_id))

    rows = []
    for p in practicals:
        c = course_by_id.get(p.course_id)
        enrolled_ids = enrollments.get(p.course_id, [])
        enrolled = len(enrolled_ids)
        submitted = sum(1 for sid in enrolled_ids if (p.id, sid) in submitted_set)
        overdue = 0
        if p.due_at and p.due_at < now:
            overdue = sum(1 for sid in enrolled_ids if (p.id, sid) not in submitted_set)
        completion_pct = _pct(submitted, enrolled)
        # Pacing gap: < 50% complete and due within 3 days
        pacing_gap = False
        if p.due_at:
            days_to_due = (p.due_at - now).total_seconds() / 86400
            pacing_gap = completion_pct < 50.0 and 0 <= days_to_due <= 3

        rows.append({
            "practical_id": p.id,
            "practical_title": p.title,
            "course_code": c.code if c else "?",
            "due_at": p.due_at.isoformat() if p.due_at else None,
            "enrolled": enrolled,
            "submitted": submitted,
            "overdue": overdue,
            "completion_pct": completion_pct,
            "pacing_gap": pacing_gap,
        })

    return rows


def faculty_at_risk_students(
    courses: list[CourseRecord],
    practicals: list[PracticalRecord],
    enrollments: dict[str, list[str]],
    submissions: list[SubmissionRecord],
    hints: list[HintLogRecord],
    students: dict[str, UserRecord],
    now: datetime | None = None,
) -> list[dict]:
    """Deterministic per-student risk score + reasons + recommended action."""
    now = now or _utcnow()

    # Map practical_id → practical
    practical_by_id = {p.id: p for p in practicals}
    # Collect all unique student IDs enrolled in these courses
    all_students: set[str] = set()
    for cid in {p.course_id for p in practicals}:
        all_students.update(enrollments.get(cid, []))

    # Build course codes per student
    student_courses: dict[str, list[str]] = defaultdict(list)
    for c in courses:
        for sid in enrollments.get(c.id, []):
            student_courses[sid].append(c.code)

    # Group all submissions by (practical_id, student_id)
    subs_by_key: dict[tuple[str, str], list[SubmissionRecord]] = defaultdict(list)
    for s in submissions:
        subs_by_key[(s.practical_id, s.student_id)].append(s)

    # Best submission per student per practical
    best = best_scores(submissions)

    # Hint counts per student per practical
    hints_by_sp: Counter = Counter((h.practical_id, h.student_id) for h in hints)

    out = []
    for sid in all_students:
        stu = students.get(sid)
        # Assigned practicals: those in courses the student is enrolled in
        enrolled_practicals = [p for p in practicals if sid in enrollments.get(p.course_id, [])]
        # Due practicals (past due or no due date)
        due_practicals = [
            p for p in enrolled_practicals
            if p.due_at is None or p.due_at <= now
        ] or enrolled_practicals

        if not due_practicals:
            continue

        done = [best[(p.id, sid)] for p in due_practicals if (p.id, sid) in best]
        scores_pct = [
            100.0 * s.final_score / s.max_score
            for s in done
            if s.final_score is not None and s.max_score
        ]
        completion_rate = _pct(len(done), len(due_practicals))
        avg_score = _mean(scores_pct)

        # Overdue: past due date and not submitted
        overdue_count = sum(
            1 for p in enrolled_practicals
            if p.due_at and p.due_at < now and (p.id, sid) not in best
        )

        # Stagnant: score < RISK_STAGNANT_SCORE on 2+ submissions of the same practical
        stagnant = False
        for p in enrolled_practicals:
            all_subs = subs_by_key.get((p.id, sid), [])
            if len(all_subs) >= 2:
                low_score_subs = [
                    s for s in all_subs
                    if s.final_score is not None and s.max_score and
                    (100.0 * s.final_score / s.max_score) < RISK_STAGNANT_SCORE
                ]
                if len(low_score_subs) >= 2:
                    stagnant = True
                    break

        # Hint overuse: > 5 hints on a practical without passing
        hint_overuse = False
        for p in enrolled_practicals:
            hint_count = hints_by_sp.get((p.id, sid), 0)
            best_sub = best.get((p.id, sid))
            if hint_count > 5 and (best_sub is None or not (best_sub.tests_total and best_sub.tests_passed == best_sub.tests_total)):
                hint_overuse = True
                break

        # Deterministic risk score (0-100)
        risk_score = 0
        risk_reasons: list[str] = []
        if completion_rate < RISK_LOW_COMPLETION:
            risk_score += 40
            risk_reasons.append(f"Low completion ({round(completion_rate)}%)")
        if avg_score is not None and avg_score < RISK_LOW_SCORE:
            risk_score += 25
            risk_reasons.append(f"Low average score ({round(avg_score)}%)")
        if overdue_count >= RISK_OVERDUE_MIN:
            risk_score += 20
            risk_reasons.append(f"{overdue_count} overdue practicals")
        if stagnant:
            risk_score += 15
            risk_reasons.append("Stagnant performance on repeated attempts")
        if hint_overuse:
            risk_score += 10
            risk_reasons.append("Excessive hint usage without passing")

        if risk_score == 0:
            continue  # not at risk — skip to keep response lean

        risk_level = "high" if risk_score >= RISK_HIGH else ("medium" if risk_score >= RISK_MED else "low")

        # Recommended action
        if risk_level == "high":
            action = "Schedule immediate one-on-one session and review overdue submissions."
        elif completion_rate < RISK_LOW_COMPLETION:
            action = "Send a nudge email and check for blockers preventing lab access."
        elif stagnant:
            action = "Review tutoring logs and suggest concept-review resources."
        else:
            action = "Monitor for one more week; reach out if score doesn't improve."

        out.append({
            "student_id": sid,
            "student_name": stu.full_name if stu else "Unknown",
            "roll_number": stu.roll_number if stu else None,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "completion_rate": completion_rate,
            "avg_score_pct": avg_score,
            "overdue_count": overdue_count,
            "courses": sorted(set(student_courses.get(sid, []))),
            "recommended_action": action,
        })

    out.sort(key=lambda r: (-r["risk_score"], r["completion_rate"]))
    return out


def faculty_difficulty_heatmap(
    courses: list[CourseRecord],
    practicals: list[PracticalRecord],
    executions: list[ExecutionLogRecord],
    hints: list[HintLogRecord],
) -> list[dict]:
    """Per-test-assertion fail rate, students failed, hint requests — sorted by severity."""
    course_by_id = {c.id: c for c in courses}
    practical_by_id = {p.id: p for p in practicals}

    attempts: Counter = Counter()   # (practical_id, test_name) → int
    fails: Counter = Counter()
    students_failed: dict[tuple, set] = defaultdict(set)

    for e in executions:
        if e.mode != "test" or e.practical_id not in practical_by_id:
            continue
        for t in e.test_results:
            key = (e.practical_id, t.name)
            attempts[key] += 1
            if not t.passed:
                fails[key] += 1
                students_failed[key].add(e.student_id)

    hint_counts: Counter = Counter((h.practical_id, h.focus_test) for h in hints if h.focus_test)

    rows = []
    for key, n in attempts.items():
        pid, test_name = key
        if n < 2 or fails[key] == 0:
            continue
        p = practical_by_id[pid]
        c = course_by_id.get(p.course_id)
        rows.append({
            "course_code": c.code if c else "?",
            "practical_title": p.title,
            "test_name": test_name,
            "fail_rate": _pct(fails[key], n),
            "students_failed": len(students_failed[key]),
            "attempts": n,
            "hint_requests": hint_counts.get(key, 0),
        })

    rows.sort(key=lambda r: (r["students_failed"] * r["fail_rate"], r["hint_requests"]), reverse=True)
    return rows


# ===========================================================================
# HOD-SCOPED INTELLIGENCE (department-wide)
# ===========================================================================

def hod_faculty_workload(d: DeptData, now: datetime | None = None) -> dict:
    """Per-faculty workload: courses, practicals, pending review, turnaround, completion."""
    now = now or _utcnow()
    week_ago = now - timedelta(days=7)

    course_by_id = d.course_by_id
    practical_to_course: dict[str, str] = {p.id: p.course_id for p in d.practicals}

    # Build per-faculty data
    faculty_data: dict[str, dict] = {}
    for fid, f in d.faculty.items():
        faculty_courses = [c for c in d.courses if c.faculty_id == fid]
        faculty_course_ids = {c.id for c in faculty_courses}
        faculty_practical_ids = {p.id for p in d.practicals if p.course_id in faculty_course_ids}

        faculty_subs = [s for s in d.submissions if s.practical_id in faculty_practical_ids]
        pending = [s for s in faculty_subs if s.status == "graded"]
        reviewed = [s for s in faculty_subs if s.status == "reviewed"]
        reviewed_week = [s for s in reviewed if s.reviewed_at and s.reviewed_at >= week_ago]

        turnaround: list[float] = []
        for s in reviewed:
            if s.reviewed_at and s.submitted_at:
                td = (s.reviewed_at - s.submitted_at).total_seconds() / 86400
                turnaround.append(max(0.0, td))

        oldest_days: float | None = None
        if pending:
            oldest = min(s.submitted_at for s in pending)
            oldest_days = round((now - oldest).total_seconds() / 86400, 1)

        # Avg completion rate across their courses
        completion_rates = []
        for cid in faculty_course_ids:
            enrolled_ids = d.enrollments.get(cid, [])
            cps = [p for p in d.practicals if p.course_id == cid]
            best = best_scores([s for s in faculty_subs if any(p.id == s.practical_id for p in cps)])
            submitted = sum(1 for p in cps for sid in enrolled_ids if (p.id, sid) in best)
            total = sum(len(enrolled_ids) for _ in cps)
            if total:
                completion_rates.append(_pct(submitted, total))

        faculty_data[fid] = {
            "faculty_id": fid,
            "faculty_name": f.full_name,
            "courses_taught": len(faculty_courses),
            "practicals_count": len(faculty_practical_ids),
            "pending_review": len(pending),
            "oldest_pending_days": oldest_days,
            "avg_turnaround_days": _mean(turnaround),
            "avg_completion_rate": _mean(completion_rates),
            "workload_flag": False,  # filled below
        }

    # Flag imbalance: pending > 2x dept avg
    all_pending = [v["pending_review"] for v in faculty_data.values()]
    dept_avg = statistics.mean(all_pending) if all_pending else 0.0
    for fid in faculty_data:
        if dept_avg > 0 and faculty_data[fid]["pending_review"] > 2 * dept_avg:
            faculty_data[fid]["workload_flag"] = True

    result = sorted(faculty_data.values(), key=lambda r: -r["pending_review"])
    return {
        "generated_at": now.isoformat(),
        "dept_avg_pending": round(dept_avg, 1),
        "faculty": result,
    }


def hod_at_risk_extended(d: DeptData, now: datetime | None = None) -> list[dict]:
    """Extended at-risk with risk score, reasons, and recommended actions (dept-wide)."""
    return faculty_at_risk_students(
        courses=d.courses,
        practicals=d.practicals,
        enrollments=d.enrollments,
        submissions=d.submissions,
        hints=d.hints,
        students=d.students,
        now=now,
    )


def hod_completion(d: DeptData, now: datetime | None = None) -> list[dict]:
    """Dept-wide completion tracking across all practicals."""
    return faculty_completion_tracking(
        courses=d.courses,
        practicals=d.practicals,
        enrollments=d.enrollments,
        submissions=d.submissions,
        now=now,
    )


def hod_difficulty_heatmap(d: DeptData) -> list[dict]:
    """Dept-wide difficulty heatmap."""
    return faculty_difficulty_heatmap(
        courses=d.courses,
        practicals=d.practicals,
        executions=d.executions,
        hints=d.hints,
    )


def hod_student_performance(d: DeptData) -> dict:
    """Dept-wide student performance."""
    return faculty_student_performance(
        courses=d.courses,
        practicals=d.practicals,
        enrollments=d.enrollments,
        submissions=d.submissions,
        hints=d.hints,
    )
