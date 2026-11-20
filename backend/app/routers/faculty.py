from __future__ import annotations

import json
import statistics

from fastapi import APIRouter, HTTPException

from app.content import TEMPLATES
from app.deps import Svc, staff_course, staff_courses, staff_practical, staff_submission
from app.execution.base import ExecutionRequest, ExecutionResult
from app.execution.service import ExecutionInputError
from app.models import LAB_FILENAME, LAB_LANGUAGE, LabType, PracticalRecord, utcnow
from app.schemas import (
    AlertsResponse,
    FilesBody,
    LockAlert,
    MentorLockBody,
    MonitorResponse,
    MonitorRow,
    GenerateTestsRequest,
    GenerateTestsResponse,
    PracticalInput,
    PracticalOut,
    ProctorEventOut,
    ReviewRequest,
    SubmissionOut,
    TemplateOut,
    TutorTranscriptOut,
)
from app.routers.tutor import transcript_out
from app.security import FacultyUser
from app.services import exam
from app.services.analytics import faculty_practical_stats
from app.services.views import courses_out, practical_out, submissions_out

router = APIRouter(prefix="/api/faculty", tags=["faculty"])


def _validate_input(body: PracticalInput) -> None:
    required = LAB_FILENAME[body.lab_type]
    if required not in body.starter_files:
        raise HTTPException(status_code=422, detail=f"{body.lab_type} labs need a starter file named '{required}'")
    if body.lab_type == "notebook":
        try:
            nb = json.loads(body.starter_files[required])
            assert isinstance(nb.get("cells"), list)
        except (json.JSONDecodeError, AssertionError, AttributeError):
            raise HTTPException(status_code=422, detail="data.ipynb must be nbformat JSON with a 'cells' list")
    names = [t.name for t in body.test_cases]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="test names must be unique")
    if body.lab_type == "worksheet":
        try:
            json.loads(body.starter_files[required])
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="answers.json must be JSON")
    for t in body.test_cases:
        if body.lab_type == "circuit" and not (t.inputs and t.expected):
            raise HTTPException(status_code=422, detail=f"circuit test '{t.name}' needs inputs and expected outputs")
        if body.lab_type != "circuit" and not (t.code and t.code.strip()):
            raise HTTPException(status_code=422, detail=f"test '{t.name}' needs Python assert code")
    ids = [r.id for r in body.rubric]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="rubric criterion ids must be unique")
    if body.status == "published" and not body.test_cases:
        raise HTTPException(status_code=422, detail="add at least one test case before publishing")
    if body.lockdown_mode == "seb" and not body.seb_config_key:
        raise HTTPException(status_code=422, detail="Safe Exam Browser mode needs the SEB Config Key of your exam config")
    if body.lockdown_mode != "off":
        body.proctored = True  # lockdown always records proctoring telemetry


@router.get("/dashboard")
async def dashboard(user: FacultyUser, svc: Svc):
    repo = svc.repo
    courses = await staff_courses(svc, user)
    course_by_id = {c.id: c for c in courses}
    practicals = await repo.list_practicals(list(course_by_id))
    pids = [p.id for p in practicals]
    subs = await repo.list_submissions(practical_ids=pids) if pids else []
    enroll = await repo.list_enrollments(list(course_by_id))
    stats = faculty_practical_stats(practicals, enroll, subs)
    scores = [s.final_score / s.max_score * 10 for s in subs if s.final_score is not None]
    return {
        "courses": await courses_out(repo, courses),
        "practicals": [
            {
                "id": p.id, "title": p.title, "course_id": p.course_id, "course_code": course_by_id[p.course_id].code,
                "lab_type": p.lab_type, "status": p.status, "due_at": p.due_at, "max_score": p.max_score,
                "proctored": p.proctored, "lockdown_mode": p.lockdown_mode,
                **stats[p.id],
            }
            for p in practicals
        ],
        "recent_submissions": await submissions_out(repo, subs[:10], {p.id: p for p in practicals}, course_by_id,
                                                   include_integrity=True),
        "stats": {
            "courses": len(courses),
            "practicals": len(practicals),
            "submissions": len(subs),
            "pending_review": sum(1 for s in subs if s.status == "graded"),
            "avg_score": round(statistics.mean(scores), 1) if scores else None,
        },
    }


@router.get("/templates/{lab_type}", response_model=TemplateOut)
async def template(lab_type: LabType, user: FacultyUser):
    t = TEMPLATES[lab_type]
    return TemplateOut(description=t["description"], starter_files=t["starter_files"],
                       test_cases=t["test_cases"], rubric=t["rubric"], worksheet=t.get("worksheet"))


@router.post("/practicals", response_model=PracticalOut, status_code=201)
async def create_practical(body: PracticalInput, user: FacultyUser, svc: Svc):
    course = await staff_course(svc, user, body.course_id)
    _validate_input(body)
    if body.lab_type == "worksheet" and body.worksheet is None:
        raise HTTPException(status_code=422, detail="worksheet labs need a worksheet layout")
    rec = PracticalRecord(
        course_id=course.id, title=body.title, description=body.description, lab_type=body.lab_type,
        language=LAB_LANGUAGE[body.lab_type], starter_files=body.starter_files, test_cases=body.test_cases,
        rubric=body.rubric, max_score=body.max_score, due_at=body.due_at, status=body.status,
        proctored=body.proctored, lockdown_mode=body.lockdown_mode, seb_config_key=body.seb_config_key,
        seb_config_url=body.seb_config_url, worksheet=body.worksheet if body.lab_type == "worksheet" else None,
        created_by=user.id,
    )
    rec = await svc.repo.create_practical(rec)
    return practical_out(rec, course, include_hidden=True)


@router.get("/practicals/{practical_id}", response_model=PracticalOut)
async def get_practical(practical_id: str, user: FacultyUser, svc: Svc):
    p, course = await staff_practical(svc, user, practical_id)
    return practical_out(p, course, include_hidden=True)


@router.put("/practicals/{practical_id}", response_model=PracticalOut)
async def update_practical(practical_id: str, body: PracticalInput, user: FacultyUser, svc: Svc):
    p, _ = await staff_practical(svc, user, practical_id)
    course = await staff_course(svc, user, body.course_id)  # may move to another course the user teaches
    _validate_input(body)
    # the practical form doesn't edit worksheet layouts yet, so an update without one keeps the current layout
    worksheet = (body.worksheet or p.worksheet) if body.lab_type == "worksheet" else None
    if body.lab_type == "worksheet" and worksheet is None:
        raise HTTPException(status_code=422, detail="worksheet labs need a worksheet layout")
    updated = p.model_copy(update={
        "course_id": course.id, "title": body.title, "description": body.description, "lab_type": body.lab_type,
        "language": LAB_LANGUAGE[body.lab_type], "starter_files": body.starter_files, "test_cases": body.test_cases,
        "rubric": body.rubric, "max_score": body.max_score, "due_at": body.due_at, "status": body.status,
        "proctored": body.proctored, "lockdown_mode": body.lockdown_mode, "seb_config_key": body.seb_config_key,
        "seb_config_url": body.seb_config_url, "worksheet": worksheet, "updated_at": utcnow(),
    })
    return practical_out(await svc.repo.update_practical(updated), course, include_hidden=True)


@router.post("/practicals/{practical_id}/publish", response_model=PracticalOut)
async def publish(practical_id: str, user: FacultyUser, svc: Svc):
    p, course = await staff_practical(svc, user, practical_id)
    if not p.test_cases:
        raise HTTPException(status_code=422, detail="add at least one test case before publishing")
    updated = await svc.repo.update_practical(p.model_copy(update={"status": "published", "updated_at": utcnow()}))
    return practical_out(updated, course, include_hidden=True)


@router.post("/practicals/{practical_id}/validate", response_model=ExecutionResult)
async def validate(practical_id: str, body: FilesBody, user: FacultyUser, svc: Svc):
    p, _ = await staff_practical(svc, user, practical_id)
    try:
        return await svc.execution.execute(
            ExecutionRequest(lab_type=p.lab_type, files=body.files, mode="test", tests=p.test_cases)
        )
    except ExecutionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/practicals/{practical_id}/submissions", response_model=list[SubmissionOut])
async def practical_submissions(practical_id: str, user: FacultyUser, svc: Svc):
    p, course = await staff_practical(svc, user, practical_id)
    subs = await svc.repo.list_submissions(practical_ids=[p.id])
    return await submissions_out(svc.repo, subs, {p.id: p}, {course.id: course}, include_integrity=True)


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
async def get_submission(submission_id: str, user: FacultyUser, svc: Svc):
    s, p, c = await staff_submission(svc, user, submission_id)
    return (await submissions_out(svc.repo, [s], {p.id: p}, {c.id: c}, include_integrity=True))[0]


@router.get("/submissions/{submission_id}/proctor-events", response_model=list[ProctorEventOut])
async def submission_proctor_events(submission_id: str, user: FacultyUser, svc: Svc):
    """Proctoring timeline for the submitting student on this practical (typing stats: one row per session)."""
    s, p, _ = await staff_submission(svc, user, submission_id)
    events = await svc.repo.list_proctor_events(p.id, s.student_id)
    sessions = await svc.repo.list_proctor_sessions(p.id, s.student_id)
    out = [
        ProctorEventOut(id=e.id, session_id=e.session_id, type=e.event_type, detail=e.detail,
                        occurred_at=e.occurred_at, created_at=e.created_at)
        for e in events
    ] + [
        ProctorEventOut(id=f"stats-{ps.id}", session_id=ps.id, type="typing_stats", detail=ps.stats,
                        occurred_at=ps.last_seen_at, created_at=ps.last_seen_at)
        for ps in sessions if ps.stats
    ]
    return sorted(out, key=lambda e: e.occurred_at)


@router.get("/submissions/{submission_id}/tutor", response_model=TutorTranscriptOut)
async def submission_tutor(submission_id: str, user: FacultyUser, svc: Svc):
    """The submitting student's AI Lab Tutor conversation on this practical (read-only)."""
    s, p, _ = await staff_submission(svc, user, submission_id)
    return transcript_out(await svc.repo.get_tutor_thread(p.id, s.student_id))


@router.post("/submissions/{submission_id}/review", response_model=SubmissionOut)
async def review(submission_id: str, body: ReviewRequest, user: FacultyUser, svc: Svc):
    s, p, c = await staff_submission(svc, user, submission_id)
    if body.faculty_score is not None and body.faculty_score > s.max_score:
        raise HTTPException(status_code=422, detail=f"score cannot exceed {s.max_score}")
    updated = s.model_copy(update={
        "faculty_score": body.faculty_score, "faculty_comment": body.faculty_comment,
        "status": "reviewed", "reviewed_at": utcnow(),
    })
    updated = await svc.repo.update_submission(updated)
    return (await submissions_out(svc.repo, [updated], {p.id: p}, {c.id: c}, include_integrity=True))[0]


@router.post("/ai/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(body: GenerateTestsRequest, user: FacultyUser, svc: Svc):
    return await svc.testgen.generate(body.title, body.description, body.lab_type, body.reference_code)


# ---------------------------------------------------------------- live lab monitor & exam lockdown
@router.get("/practicals/{practical_id}/monitor", response_model=MonitorResponse)
async def monitor(practical_id: str, user: FacultyUser, svc: Svc):
    """Live view of every enrolled student on this practical (poll every few seconds)."""
    p, course = await staff_practical(svc, user, practical_id)
    rows = await exam.monitor_rows(svc.repo, p)
    counts = {k: sum(1 for r in rows if r["status"] == k)
              for k in ("not_started", "active", "paused", "locked", "submitted")}
    counts["online"] = sum(1 for r in rows if r["online"])
    return MonitorResponse(practical_id=p.id, practical_title=p.title, course_code=course.code,
                           lockdown_mode=p.lockdown_mode, proctored=p.proctored, generated_at=utcnow(),
                           counts=counts, rows=[MonitorRow(**r) for r in rows])


async def _monitor_row(svc: Svc, p, student_id: str) -> MonitorRow:
    row = next((r for r in await exam.monitor_rows(svc.repo, p) if r["student_id"] == student_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Student is not enrolled in this course")
    return MonitorRow(**row)


@router.post("/practicals/{practical_id}/exam/{student_id}/unlock", response_model=MonitorRow)
async def unlock_exam(practical_id: str, student_id: str, user: FacultyUser, svc: Svc):
    p, _ = await staff_practical(svc, user, practical_id)
    if student_id not in (await svc.repo.list_enrollments([p.course_id])).get(p.course_id, []):
        raise HTTPException(status_code=404, detail="Student is not enrolled in this course")
    await exam.unlock(svc.repo, p, student_id, user)
    return await _monitor_row(svc, p, student_id)


@router.post("/practicals/{practical_id}/exam/{student_id}/lock", response_model=MonitorRow)
async def lock_exam(practical_id: str, student_id: str, body: MentorLockBody, user: FacultyUser, svc: Svc):
    p, _ = await staff_practical(svc, user, practical_id)
    if student_id not in (await svc.repo.list_enrollments([p.course_id])).get(p.course_id, []):
        raise HTTPException(status_code=404, detail="Student is not enrolled in this course")
    await exam.mentor_lock(svc.repo, p, student_id, user, body.reason)
    return await _monitor_row(svc, p, student_id)


@router.get("/alerts", response_model=AlertsResponse)
async def alerts(user: FacultyUser, svc: Svc):
    """Students whose exams are currently locked, across the courses this user supervises."""
    courses = {c.id: c for c in await staff_courses(svc, user)}
    practicals = {p.id: p for p in await svc.repo.list_practicals(list(courses)) if p.lockdown_mode != "off"}
    locked = [a for a in await svc.repo.list_exam_attempts(list(practicals)) if a.status == "locked"]
    users = await svc.repo.get_users([a.student_id for a in locked])
    out = [
        LockAlert(practical_id=a.practical_id, practical_title=practicals[a.practical_id].title,
                  course_code=courses[practicals[a.practical_id].course_id].code, student_id=a.student_id,
                  student_name=users[a.student_id].full_name if a.student_id in users else "Unknown student",
                  roll_number=users[a.student_id].roll_number if a.student_id in users else None,
                  lock_reason=a.lock_reason, locked_at=a.locked_at)
        for a in locked
    ]
    out.sort(key=lambda x: x.locked_at or utcnow(), reverse=True)
    return AlertsResponse(locked_count=len(out), locked=out)
