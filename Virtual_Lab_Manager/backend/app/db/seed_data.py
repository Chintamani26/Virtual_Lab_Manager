"""Deterministic synthetic institutional data (one Computer Engineering department).

Used by the in-memory repository at startup and by scripts/generate_seed_sql.py, so both
storage modes show identical demo data. IDs are stable uuid5 values.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app import content as C
from app import worksheet_labs as W
from app.config import get_settings
from app.models import (
    LAB_LANGUAGE,
    CourseRecord,
    Department,
    DraftRecord,
    ExecutionLogRecord,
    HintLogRecord,
    PracticalRecord,
    ProctorEventRecord,
    ProctorSessionRecord,
    RubricScore,
    SubmissionRecord,
    TestCaseSpec,
    TestResult,
    UserRecord,
    utcnow,
)

# Password of every seeded demo account. Read through Settings (env var or backend/.env, default "demo1234")
# so the seeded hashes always match what /api/auth/demo-accounts offers on the one-click logins.
DEMO_PASSWORD = get_settings().demo_password
_NS = uuid.UUID("6f1c9a52-6a43-4d5e-9c63-3a2f1b7e0a11")
SEED_MODEL = "synthetic-seed"


def sid(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


@dataclass
class SeedBundle:
    departments: list[Department] = field(default_factory=list)
    users: list[UserRecord] = field(default_factory=list)
    courses: list[CourseRecord] = field(default_factory=list)
    enrollments: list[tuple[str, str]] = field(default_factory=list)
    practicals: list[PracticalRecord] = field(default_factory=list)
    drafts: list[DraftRecord] = field(default_factory=list)
    submissions: list[SubmissionRecord] = field(default_factory=list)
    execution_logs: list[ExecutionLogRecord] = field(default_factory=list)
    hint_logs: list[HintLogRecord] = field(default_factory=list)
    proctor_sessions: list[ProctorSessionRecord] = field(default_factory=list)
    proctor_events: list[ProctorEventRecord] = field(default_factory=list)


STUDENTS = [
    "Aarav Sharma", "Diya Patel", "Vivaan Gupta", "Ananya Iyer", "Aditya Kulkarni", "Ishita Deshmukh",
    "Arjun Nair", "Saanvi Reddy", "Kabir Mehta", "Myra Joshi", "Reyansh Pawar", "Anika Bhosale",
    "Vihaan Rao", "Kiara Menon", "Rohan Jadhav", "Tara Shetty", "Ishaan Chavan", "Meher Kapoor",
    "Atharv Gokhale", "Riya Banerjee", "Shaurya Thakur", "Navya Pillai", "Dhruv Agarwal", "Avni Saxena",
]
AT_RISK = {"Kabir Mehta", "Rohan Jadhav", "Ishaan Chavan"}
DEMO_STUDENT = "Aarav Sharma"

# Lab 4 academic-integrity case studies shown on the faculty dashboard
INTEGRITY_CASES = {"Vihaan Rao": "ai", "Riya Banerjee": "peer_source", "Dhruv Agarwal": "peer_copy"}

FACULTY = ["Meera Kulkarni", "Sanjay Patil", "Neha Joshi", "Amit Verma", "Kavita Rao"]
HOD = "Rajesh Deshpande"


def email_for(name: str) -> str:
    return name.lower().replace(" ", ".") + "@demo.edu"


# Per-test difficulty multipliers drive which tests become departmental bottlenecks.
DIFFICULTY = {
    "test_duplicate_keys": 2.8,
    "test_skewed_tree": 0.9,
    "test_height": 0.6,
    "test_delete_head": 1.2,
    "test_reverse": 0.8,
    # MA201 numerical methods worksheet
    "test_nr_df_x0": 0.9,
    "test_nr_x1": 1.2,
    "test_nr_x2": 0.8,
    "test_nr_root": 0.9,
    "test_sr_odd": 1.3,
    "test_sr_integral": 1.0,
    "test_sr_pi": 0.6,
    # PH101 pendulum experiment
    "test_readings": 0.4,
    "test_periods": 0.5,
    "test_t_squared": 0.4,
    "test_slope": 1.3,
    "test_g_value": 0.9,
    "test_percent_error": 1.0,
    # EE210 Ohm's law bench
    "test_r_column": 1.5,
    "test_r_from_graph": 1.4,
    "test_r_mean": 0.5,
    "test_power": 0.9,
    "test_max_voltage": 1.1,
    "test_readings_genuine": 0.0,  # seeded students all used the instruments
    "test_r_accuracy": 0.3,
}

FEEDBACK = {
    "test_duplicate_keys": "Duplicate keys are inserted again instead of being ignored — revisit the equality case in insert().",
    "test_skewed_tree": "Height computation struggles on skewed input; consider how the longest path is measured.",
    "test_delete_head": "Deleting the head node does not update the head pointer.",
    "test_reverse_empty": "reverse() should be a no-op on an empty list.",
    "test_nr_f_x0": "f(x₀) has a sign slip when substituting x₀ = 2.",
    "test_nr_df_x0": "f′(x₀) is wrong: differentiate f(x) before substituting.",
    "test_nr_x1": "The Newton–Raphson update moved the wrong way (sign of f(x₀)/f′(x₀)).",
    "test_nr_f_x1": "f(x₁) is not accurate to 4 decimal places.",
    "test_nr_df_x1": "f′(x₁) is not the derivative evaluated at x₁.",
    "test_nr_x2": "The second iteration does not follow from x₁.",
    "test_nr_root": "The root is not correct to 4 decimal places.",
    "test_sr_h": "The strip width h is wrong.",
    "test_sr_ends": "The end ordinates y₀ + y₄ are wrong.",
    "test_sr_odd": "The odd ordinates were not weighted by 4.",
    "test_sr_even": "The even ordinate was not weighted by 2.",
    "test_sr_integral": "The Simpson's sum was not multiplied by h / 3.",
    "test_sr_pi": "The estimate of π should be 4 × I.",
    "test_readings": "Too few readings, or the lengths do not cover a wide enough range.",
    "test_periods": "T was not divided by 10: the stopwatch timed 10 oscillations.",
    "test_t_squared": "The T² column is not T multiplied by itself.",
    "test_slope": "The slope does not match the best-fit line of the T²–L graph.",
    "test_g_value": "g should be 4π² divided by the slope of the T²–L line.",
    "test_percent_error": "Percentage error should be |g − 9.81| / 9.81 × 100.",
    "test_r_column": "R was computed with the current in mA instead of amperes.",
    "test_r_from_graph": "The slope was left in volts per milliampere instead of ohms.",
    "test_r_mean": "The mean of the R column is wrong.",
    "test_power": "Power at 9 V should use P = V² / R.",
    "test_max_voltage": "The safe-voltage limit should come from P = V² / R with P = 0.5 W.",
}

PRAISE = {
    "bst": "Clean BST implementation with correct traversal and min/max logic.",
    "linked_list": "Well-structured linked list with clear pointer manipulation.",
    "numerical_methods": "Careful step-by-step working with every value to the requested precision.",
    "pendulum": "Accurate pendulum readings with a clean T²–L analysis.",
    "ohms_law": "Good spread of readings with a correct V–I analysis and units.",
}


def _practicals(now: datetime, dept_courses: dict[str, str], faculty_ids: dict[str, str]) -> dict[str, PracticalRecord]:
    def p(slug, course, title, desc, lab_type, starter, tests, rubric, due, created, status="published", author=None):
        return PracticalRecord(
            id=sid(f"practical:{slug}"),
            course_id=dept_courses[course],
            title=title,
            description=desc,
            lab_type=lab_type,
            language=LAB_LANGUAGE[lab_type],
            starter_files=starter,
            test_cases=tests,
            rubric=rubric,
            max_score=10,
            due_at=due,
            status=status,
            created_by=author,
            created_at=created,
            updated_at=created,
        )

    meera, sanjay, neha = faculty_ids["Meera Kulkarni"], faculty_ids["Sanjay Patil"], faculty_ids["Neha Joshi"]
    kavita = faculty_ids["Kavita Rao"]
    d = lambda days, hours=0: now + timedelta(days=days, hours=hours)  # noqa: E731
    labs = {
        "linked_list": p("linked_list", "CS201", "Lab 3: Singly Linked Lists", C.LL_DESCRIPTION, "coding",
                         {"main.py": C.LL_STARTER}, C.LL_TESTS, C.LL_RUBRIC, d(-7, 6), d(-21), author=meera),
        "bst": p("bst", "CS201", "Lab 4: Binary Search Trees", C.BST_DESCRIPTION, "coding",
                 {"main.py": C.BST_STARTER}, C.BST_TESTS, C.BST_RUBRIC, d(3, 6), d(-6), author=meera),  # lockdown set below
        "graph": p("graph", "CS201", "Lab 5: Graph Traversal (BFS/DFS)", C.GRAPH_DESCRIPTION, "coding",
                   {"main.py": C.GRAPH_STARTER}, C.GRAPH_TESTS, C.GRAPH_RUBRIC, d(12, 6), d(-1), status="draft", author=meera),
        # worksheet labs: step-by-step maths and virtual experiments, no code (app/worksheet_labs.py)
        "ohms_law": p("ohms_law", "EE210", "Lab 1: Ohm's Law — V–I Characteristic", W.OHM_DESCRIPTION, "worksheet",
                      {"answers.json": W.EMPTY_ANSWERS}, W.OHM_TESTS, W.EXPERIMENT_RUBRIC, d(5, 6), d(-5),
                      author=sanjay),
        "numerical_methods": p("numerical_methods", "MA201", "Lab 2: Newton–Raphson and Simpson's Rule",
                               W.NM_DESCRIPTION, "worksheet", {"answers.json": W.EMPTY_ANSWERS}, W.NM_TESTS,
                               W.NM_RUBRIC, d(2, 6), d(-8), author=neha),
        "pendulum": p("pendulum", "PH101", "Lab 1: Simple Pendulum — Measuring g", W.PENDULUM_DESCRIPTION, "worksheet",
                      {"answers.json": W.EMPTY_ANSWERS}, W.PENDULUM_TESTS, W.EXPERIMENT_RUBRIC, d(-4, 6), d(-18),
                      author=kavita),
    }
    labs["bst"].lockdown_mode = "exam"  # hero demo: strict exam mode (lock on leaving, mentor unlock)
    labs["ohms_law"].worksheet = W.OHM_WORKSHEET
    labs["numerical_methods"].worksheet = W.NM_WORKSHEET
    labs["pendulum"].worksheet = W.PENDULUM_WORKSHEET
    return labs


# participation / completion probabilities per practical
ENGAGEMENT = {
    "linked_list": (0.95, 0.95),
    "bst": (0.75, 0.7),
    "ohms_law": (0.45, 0.55),
    "numerical_methods": (0.6, 0.6),
    "pendulum": (0.9, 0.9),
}


# Questions students typed with their hint requests (demo data for the Learning Difficulty Analyzer). Picked by a
# hash of the hint id, not the seeded RNG, so the rest of the seed (and the tuned demo numbers) doesn't change.
SEED_QUESTIONS: dict[str, list[str]] = {
    "test_duplicate_keys": [
        "what happens when two values are equal?", "why does my size go up when I insert 8 twice?",
        "should equal keys go left or right?", "do I need a separate case for equal keys?",
        "why is inorder showing 3 twice?",
    ],
    "test_prepend": ["does prepend need to update the size too?", "what should head point to after prepend?"],
    "test_height": ["is the height of an empty tree 0 or -1?", "why is my height off by one?"],
    "test_reverse": ["how do I reverse without losing the rest of the list?"],
    "test_r_column": ["do I divide volts by milliamps directly?", "why is my resistance 1000 times too small?",
                      "should current be in amps or mA for R = V/I?"],
    "test_r_from_graph": ["which axis is voltage on the V-I graph?", "how do I get resistance from the slope?"],
    "test_slope": ["how do I find the slope of T² against L?", "should I use two points or all readings for the slope?",
                   "is the slope 4π²/g or g/4π²?"],
    "test_percent_error": ["what value of g do I compare with?"],
    "test_sr_odd": ["which ordinates get the weight 4 in Simpson's rule?", "is y2 an odd or even ordinate?"],
    "test_nr_root": ["how many iterations do I need for 4 decimal places?"],
}


def _seed_question(focus: str, hint_id: str) -> str | None:
    pool = SEED_QUESTIONS.get(focus)
    if not pool:
        return None
    h = int(uuid.uuid5(uuid.NAMESPACE_URL, hint_id).hex[:8], 16)
    return pool[h % len(pool)] if h % 10 < 6 else None


def _fail(rng: random.Random, test: TestCaseSpec, skill: float, attempt_factor: float) -> bool:
    base = DIFFICULTY.get(test.name, 0.35)
    return rng.random() < min(0.95, base * (1.05 - skill) * attempt_factor)


def _breakdown(rng: random.Random, prac: PracticalRecord, pass_ratio: float, skill: float) -> list[RubricScore]:
    out = []
    for crit in prac.rubric:
        if crit.id == "correctness":
            frac = pass_ratio
        elif crit.id in ("edge_cases", "visited"):
            frac = min(1.0, pass_ratio * (0.6 + 0.4 * skill))
        else:
            frac = min(1.0, max(0.2, skill + rng.uniform(-0.25, 0.05)))
        score = round(crit.max_points * frac * 2) / 2  # half-point steps
        out.append(
            RubricScore(
                criterion_id=crit.id, name=crit.name, score=score, max_points=crit.max_points,
                feedback="Meets expectations." if frac > 0.85 else ("Partially meets expectations." if frac > 0.5 else "Needs work."),
            )
        )
    return out


def build_seed(now: datetime | None = None, password_hash: str | None = None) -> SeedBundle:
    from app.security import hash_password

    now = (now or utcnow()).replace(microsecond=0)
    rng = random.Random(2026)
    pwd = password_hash or hash_password(DEMO_PASSWORD)
    b = SeedBundle()

    dept = Department(
        id=sid("dept:ce"), name="Computer Engineering", code="CE",
        institution_name="Deccan Institute of Engineering (Demo)", created_at=now - timedelta(days=400),
    )
    b.departments.append(dept)

    def user(name: str, role: str, roll: str | None = None) -> UserRecord:
        u = UserRecord(
            id=sid(f"user:{email_for(name)}"), email=email_for(name), password_hash=pwd, full_name=name,
            role=role, department_id=dept.id, roll_number=roll, created_at=now - timedelta(days=120),
        )
        b.users.append(u)
        return u

    hod = user(HOD, "hod")
    faculty = {n: user(n, "faculty") for n in FACULTY}
    students = [user(n, "student", f"CE23{i + 1:03d}") for i, n in enumerate(STUDENTS)]
    _ = hod

    # one lab course per discipline: coding, physics, maths, electrical
    course_defs = [
        ("CS201", "Data Structures Lab", 3, "Meera Kulkarni"),
        ("PH101", "Physics Lab", 2, "Kavita Rao"),
        ("MA201", "Applied Mathematics Lab", 3, "Neha Joshi"),
        ("EE210", "Electrical Lab", 3, "Sanjay Patil"),
        ("CS305", "Operating Systems Lab", 5, None),  # unassigned: HOD assigns faculty in the demo
    ]
    # Course ids are uuid5("course:<code>") except where a course was renamed: EE210 keeps the id it had as EC210,
    # so re-seeding an existing Firestore project updates that course in place instead of leaving a stale copy.
    id_key = {"EE210": "EC210"}
    course_ids: dict[str, str] = {}
    for code, title, sem, fac in course_defs:
        c = CourseRecord(
            id=sid(f"course:{id_key.get(code, code)}"), department_id=dept.id, code=code, title=title, semester=sem,
            faculty_id=faculty[fac].id if fac else None, created_at=now - timedelta(days=90),
        )
        b.courses.append(c)
        course_ids[code] = c.id

    enrolled: dict[str, list[UserRecord]] = {
        "CS201": students,
        "PH101": students,
        "MA201": students[:12],
        "EE210": students,
        "CS305": [],  # next semester's course: no enrolments yet, so students see only the four courses above
    }
    for code, studs in enrolled.items():
        b.enrollments.extend((course_ids[code], s.id) for s in studs)

    practicals = _practicals(now, course_ids, {n: f.id for n, f in faculty.items()})
    b.practicals.extend(practicals.values())
    course_of = {"linked_list": "CS201", "bst": "CS201", "ohms_law": "EE210", "numerical_methods": "MA201",
                 "pendulum": "PH101"}

    # the hero demo draft
    demo = next(s for s in students if s.full_name == DEMO_STUDENT)
    b.drafts.append(
        DraftRecord(practical_id=practicals["bst"].id, student_id=demo.id,
                    files={"main.py": C.BST_DEMO_DRAFT}, updated_at=now - timedelta(hours=20))
    )

    skill = {
        s.id: (rng.uniform(0.15, 0.35) if s.full_name in AT_RISK else rng.uniform(0.35, 0.95)) for s in students
    }
    skill[demo.id] = 0.82

    for slug, prac in practicals.items():
        if slug == "graph":
            continue
        p_join, p_complete = ENGAGEMENT[slug]
        visible = [t for t in prac.test_cases if not t.hidden]
        window_start = prac.created_at + timedelta(hours=6)
        window_end = min(now - timedelta(hours=1), prac.due_at or now)
        for s in enrolled[course_of[slug]]:
            if s.id == demo.id and slug in ("bst", "ohms_law", "numerical_methods"):
                continue  # keep the demo student's open labs clean for the live walkthrough
            sk = skill[s.id]
            join = p_join * (0.5 if s.full_name in AT_RISK else 1.0)
            case = INTEGRITY_CASES.get(s.full_name) if slug == "bst" else None
            if s.id != demo.id and rng.random() > join and not case:
                continue
            span = (window_end - window_start).total_seconds()
            runs = rng.randint(1, 3) + (2 if sk < 0.6 else 0)
            times = sorted(window_start + timedelta(seconds=rng.uniform(0, span)) for _ in range(runs + 1))
            hint_level: dict[str, int] = {}
            last_failed: list[str] = []
            for attempt, ts in enumerate(times[:-1]):
                factor = max(0.25, 1.0 - attempt * 0.25)
                results = [
                    TestResult(name=t.name, passed=not _fail(rng, t, sk, factor), hidden=False,
                               message=None)
                    for t in visible
                ]
                for r in results:
                    if not r.passed:
                        r.message = "AssertionError: " + FEEDBACK.get(r.name, "assertion failed")
                last_failed = [r.name for r in results if not r.passed]
                ex = ExecutionLogRecord(
                    id=sid(f"exec:{slug}:{s.id}:{attempt}"), practical_id=prac.id, student_id=s.id,
                    lab_type=prac.lab_type, mode="test",
                    engine="circuit-sim" if prac.lab_type == "circuit" else "judge0",
                    status="ok", files={}, test_results=results,
                    tests_passed=sum(r.passed for r in results), tests_total=len(results),
                    duration_ms=rng.randint(40, 900), created_at=ts,
                )
                b.execution_logs.append(ex)
                if last_failed and rng.random() < 0.55:
                    focus = last_failed[0]
                    lvl = min(3, hint_level.get(focus, 0) + 1)
                    hint_level[focus] = lvl
                    hint_id = sid(f"hint:{slug}:{s.id}:{attempt}")
                    b.hint_logs.append(
                        HintLogRecord(
                            id=hint_id, practical_id=prac.id, student_id=s.id,
                            execution_id=ex.id, focus_test=focus, hint_level=lvl,
                            question=_seed_question(focus, hint_id),
                            hint_text=f"(seeded) Socratic hint level {lvl} for {focus}",
                            model=SEED_MODEL, source="fallback", created_at=ts + timedelta(minutes=2),
                        )
                    )

            completes = rng.random() < p_complete * (0.45 if s.full_name in AT_RISK else 1.0)
            if s.id == demo.id or case:
                completes = True
            if not completes:
                continue
            final = [
                TestResult(name=t.name, passed=not _fail(rng, t, sk, 0.8), hidden=t.hidden)
                for t in prac.test_cases
            ]
            if s.id == demo.id or case:
                final = [TestResult(name=t.name, passed=True, hidden=t.hidden) for t in prac.test_cases]
            failed = [r.name for r in final if not r.passed]
            for r in final:
                if not r.passed:
                    r.message = "AssertionError: " + FEEDBACK.get(r.name, "assertion failed")
            worksheet_files = None
            if prac.lab_type == "worksheet":
                # Answers with the drawn mistakes, then the real checks decide the results, so a seeded submission
                # always re-checks to what it shows (checks depend on each other, e.g. a wrong slope makes g wrong).
                # Own random stream per student, so worksheet answers don't shift the rest of the seed.
                answers = W.seed_answers(slug, random.Random(f"{slug}:{s.id}"), set(failed))
                final = W.evaluate(prac.test_cases, answers)
                failed = [r.name for r in final if not r.passed]
                worksheet_files = {"answers.json": json.dumps(answers)}
            ratio = sum(r.passed for r in final) / len(final)
            breakdown = _breakdown(rng, prac, ratio, sk)
            total = round(sum(x.score for x in breakdown), 1)
            if case:
                files = {"main.py": C.BST_AI_STYLE if case == "ai" else C.BST_PEER_SOLUTION}
            elif slug == "bst" and "test_duplicate_keys" in failed:
                files = {"main.py": C.BST_DEMO_DRAFT}
            elif worksheet_files is not None:
                files = worksheet_files
            elif not failed:
                files = dict(C.REFERENCE_SOLUTIONS[slug])
            else:
                files = dict(C.REFERENCE_SOLUTIONS[slug]) if ratio > 0.6 else dict(prac.starter_files)
            feedback = PRAISE[slug] if not failed else " ".join(
                [PRAISE[slug].split(" with ")[0] + "."] + [FEEDBACK.get(n, f"{n} fails.") for n in failed[:2]]
            )
            submitted_at = times[-1]
            sub = SubmissionRecord(
                id=sid(f"submission:{slug}:{s.id}"), practical_id=prac.id, student_id=s.id, files=files,
                status="graded", tests_passed=sum(r.passed for r in final), tests_total=len(final),
                test_results=final, rubric_score=total, max_score=prac.max_score, rubric_breakdown=breakdown,
                ai_feedback=feedback, grading_model=SEED_MODEL, submitted_at=submitted_at,
                graded_at=submitted_at + timedelta(seconds=4),
            )
            past_due = prac.due_at is not None and prac.due_at < now
            if past_due and rng.random() < 0.35:
                sub.status = "reviewed"
                sub.faculty_score = min(prac.max_score, round(total + rng.choice([0, 0.5, 1.0]), 1))
                sub.faculty_comment = "Reviewed in lab viva — good understanding." if ratio > 0.8 else "Discussed fixes in lab; resubmit next time before the deadline."
                sub.reviewed_at = submitted_at + timedelta(days=2)
            b.submissions.append(sub)

    _seed_integrity(b, practicals, {u.id: u for u in students})
    return b


def _seed_integrity(b: SeedBundle, practicals: dict[str, PracticalRecord], students: dict[str, UserRecord]) -> None:
    """Synthesize proctoring telemetry for every seeded submission and compute its integrity report with the
    real analyzer (offline heuristics), so seeded and live reports are consistent."""
    from app.ai.integrity import build_report, code_text, heuristic_content, new_code_chars

    rng = random.Random(77)  # separate stream: doesn't disturb the tuned activity data above
    by_id = {p.id: p for p in practicals.values()}
    case_of = {sub.id: INTEGRITY_CASES.get(students[sub.student_id].full_name)
               for sub in b.submissions if by_id[sub.practical_id].title.startswith("Lab 4")}
    peer_subs = {c: sub for sub in b.submissions if (c := case_of.get(sub.id)) in ("peer_source", "peer_copy")}

    for sub in b.submissions:
        prac = by_id[sub.practical_id]
        case = case_of.get(sub.id)
        start = sub.submitted_at - timedelta(minutes=rng.randint(35, 110))
        new_chars = new_code_chars(code_text(prac.lab_type, prac.starter_files), code_text(prac.lab_type, sub.files))
        session = ProctorSessionRecord(
            id=sid(f"psession:{sub.id}"), practical_id=prac.id, student_id=sub.student_id,
            baseline_files=dict(prac.starter_files), started_at=start, last_seen_at=sub.submitted_at,
        )
        events: list[ProctorEventRecord] = []

        def ev(kind: str, minutes: float, **detail) -> None:
            events.append(ProctorEventRecord(
                id=sid(f"pevent:{sub.id}:{len(events)}"), practical_id=prac.id, student_id=sub.student_id,
                session_id=session.id, event_type=kind, detail=detail,
                occurred_at=start + timedelta(minutes=minutes), created_at=start + timedelta(minutes=minutes),
            ))

        ev("session_start", 0)
        if case == "ai":
            typed, large, burst = int(new_chars * 0.12), [(18, 1460), (31, 690)], 58.0
            for m in (6, 9, 17, 24, 30):
                ev("paste_blocked", m)
            ev("copy_blocked", 3)
            ev("devtools_blocked", 12)
            for m, dur in ((4, 95_000), (11, 240_000), (16, 180_000), (22, 130_000), (29, 75_000), (33, 60_000)):
                ev("focus_lost", m, duration_ms=dur, reason="tab_hidden")
            for m, chars in large:
                ev("large_insertion", m, chars=chars)
        elif case == "peer_copy":
            typed, large, burst = int(new_chars * 0.18), [(21, 980)], 26.0
            for m in (8, 14, 19):
                ev("paste_blocked", m)
            for m, dur in ((5, 200_000), (13, 160_000), (18, 70_000)):
                ev("focus_lost", m, duration_ms=dur, reason="window_blur")
            for m, chars in large:
                ev("large_insertion", m, chars=chars)
        else:
            typed, large, burst = int(new_chars * rng.uniform(1.25, 2.6)), [], round(rng.uniform(4, 11), 1)
            for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
                ev("focus_lost", rng.uniform(2, 30), duration_ms=rng.randint(4_000, 70_000),
                   reason=rng.choice(["tab_hidden", "window_blur"]))
            if rng.random() < 0.12:
                ev("paste_blocked", rng.uniform(2, 30))
            if rng.random() < 0.1:
                ev("fullscreen_exit", rng.uniform(2, 30))
        session.stats = {
            "typed_chars": typed, "keystrokes": int(typed * 1.15), "active_ms": int(typed * rng.uniform(180, 320)),
            "large_insertions": len(large), "large_insertion_chars": sum(c for _, c in large), "max_burst_cps": burst,
        }
        peers = []
        if case == "peer_source" and "peer_copy" in peer_subs:
            other = peer_subs["peer_copy"]
            peers = [(other.id, students[other.student_id].full_name, other.files)]
        elif case == "peer_copy" and "peer_source" in peer_subs:
            other = peer_subs["peer_source"]
            peers = [(other.id, students[other.student_id].full_name, other.files)]
        content = heuristic_content(prac.lab_type, code_text(prac.lab_type, sub.files),
                                    [code_text(prac.lab_type, prac.starter_files)])
        report = build_report(practical=prac, files=sub.files, sessions=[session], events=events,
                              content=content, peers=peers)
        sub.integrity = report.model_copy(update={"analyzed_at": sub.graded_at or sub.submitted_at})
        b.proctor_sessions.append(session)
        b.proctor_events.extend(events)
