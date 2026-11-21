from __future__ import annotations

import asyncio
import statistics
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request

from app.ai.integrity import code_text, proctor_summary
from app.db.seed_data import SEED_MODEL
from app.deps import Svc, student_practical
from app.execution.base import ExecutionRequest, ExecutionResult
from app.execution.service import ExecutionInputError
from app.models import (
    LAB_FILENAME,
    DraftRecord,
    ExecutionLogRecord,
    PracticalRecord,
    ProctorEventRecord,
    ProctorSessionRecord,
    SubmissionRecord,
    UserRecord,
    utcnow,
)
from app.routers.auth import user_out
from app.schemas import (
    DraftSaved,
    ExamSessionBody,
    ExamState,
    ExamViolationBody,
    FilesBody,
    HintRequest,
    HintResponse,
    LintRequest,
    LintResponse,
    ProctorBatch,
    ProctorBatchResponse,
    ProctorSummary,
    RunRequest,
    StudentPracticalOut,
    SubmissionOut,
)
from app.security import StudentUser
from app.services import exam
from app.services.views import courses_out, practical_out, submissions_out

router = APIRouter(prefix="/api/student", tags=["student"])
MAX_SUBMISSIONS_PER_PRACTICAL = 10


async def _execute(svc: Svc, req: ExecutionRequest) -> ExecutionResult:
    try:
        return await svc.execution.execute(req)
    except ExecutionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/dashboard")
async def dashboard(user: StudentUser, svc: Svc):
    repo = svc.repo
    courses = await repo.list_courses(student_id=user.id)
    course_by_id = {c.id: c for c in courses}
    practicals = await repo.list_practicals(list(course_by_id), published_only=True)
    pids = [p.id for p in practicals]
    subs = await repo.list_submissions(student_id=user.id)
    execs = await repo.list_student_execution_logs(user.id, pids)
    hints = await repo.list_hint_logs(student_id=user.id)

    rows, best_scores = [], []
    for p in practicals:
        mine = [s for s in subs if s.practical_id == p.id]
        draft = await repo.get_draft(p.id, user.id)
        p_execs = [e for e in execs if e.practical_id == p.id]
        best = max((s.final_score for s in mine if s.final_score is not None), default=None)
        if best is not None:
            best_scores.append(best / p.max_score * 10)
        if mine:
            progress = "graded" if any(s.rubric_score is not None for s in mine) else "submitted"
        elif draft or p_execs:
            progress = "in_progress"
        else:
            progress = "not_started"
        times = [s.submitted_at for s in mine] + [e.created_at for e in p_execs] + ([draft.updated_at] if draft else [])
        latest = max(mine, key=lambda s: s.submitted_at, default=None)
        c = course_by_id[p.course_id]
        rows.append({
            "id": p.id, "title": p.title, "course_id": c.id, "course_code": c.code, "course_title": c.title,
            "lab_type": p.lab_type, "due_at": p.due_at, "max_score": p.max_score, "progress": progress,
            "best_score": best, "attempts": len(mine), "last_activity_at": max(times) if times else None,
            # latest submission, so completed labs can show their result without a second request
            "submitted_at": latest.submitted_at if latest else None,
            "tests_passed": latest.tests_passed if latest else None,
            "tests_total": latest.tests_total if latest else None,
            "reviewed": bool(latest and latest.status == "reviewed"),
            "feedback": (latest.faculty_comment or latest.ai_feedback) if latest else None,
        })

    return {
        "user": user_out(user),
        "courses": await courses_out(repo, courses),
        "practicals": rows,
        "stats": {
            "assigned": len(practicals),
            "completed": sum(1 for r in rows if r["progress"] in ("graded", "submitted")),
            "avg_score": round(statistics.mean(best_scores), 1) if best_scores else None,
            "hints_used": len(hints),
        },
        "recent_submissions": (await submissions_out(repo, subs[:5])),
    }


@router.get("/practicals/{practical_id}", response_model=StudentPracticalOut)
async def get_practical(practical_id: str, user: StudentUser, svc: Svc, request: Request):
    p, course = await student_practical(svc, user, practical_id)
    draft = await svc.repo.get_draft(p.id, user.id)
    subs = await svc.repo.list_submissions(practical_ids=[p.id], student_id=user.id)
    latest = (await submissions_out(svc.repo, subs[:1], {p.id: p}, {course.id: course})) if subs else []
    hints = await svc.repo.list_hint_logs(practical_ids=[p.id], student_id=user.id)
    base = practical_out(p, course, include_hidden=False)
    summary = None
    if p.proctored:
        summary = ProctorSummary(**proctor_summary(await svc.repo.list_proctor_sessions(p.id, user.id),
                                                   await svc.repo.list_proctor_events(p.id, user.id)))
    return StudentPracticalOut(
        **base.model_dump(),
        draft_files=draft.files if draft else None,
        draft_updated_at=draft.updated_at if draft else None,
        latest_submission=latest[0] if latest else None,
        hints_used=len(hints),
        proctoring_summary=summary,
        exam=await _exam_state(svc, request, p, user, None) if p.lockdown_mode != "off" else None,
        submission_limit=MAX_SUBMISSIONS_PER_PRACTICAL,
        submissions_used=len(subs),
    )


async def _exam_state(svc: Svc, request: Request, p: PracticalRecord, user: UserRecord, session_id: str | None,
                      attempt=None) -> ExamState:
    a = attempt if attempt is not None else await exam.load_attempt(svc.repo, p.id, user.id)
    seb_ok = p.lockdown_mode == "seb" and exam.seb_verified(request, p, request.app.state.settings)
    return ExamState(**exam.exam_state(p, a, session_id, seb_ok))


async def _exam_practical(svc: Svc, user: UserRecord, practical_id: str, request: Request) -> PracticalRecord:
    p, _ = await student_practical(svc, user, practical_id)
    if p.lockdown_mode == "off":
        raise HTTPException(status_code=409, detail="This practical does not use exam lockdown")
    if p.lockdown_mode == "seb" and not exam.seb_verified(request, p, request.app.state.settings):
        raise HTTPException(status_code=403, detail="This exam must be taken in Safe Exam Browser")
    return p


@router.post("/practicals/{practical_id}/exam/start", response_model=ExamState)
async def exam_start(practical_id: str, body: ExamSessionBody, user: StudentUser, svc: Svc, request: Request):
    """Claim the exam for this browser tab. A second tab, or a new tab after the page was closed/reloaded,
    locks the exam until a mentor unlocks it."""
    p = await _exam_practical(svc, user, practical_id, request)
    a = await exam.start(svc.repo, p, user, body.session_id)
    return await _exam_state(svc, request, p, user, body.session_id, a)


@router.post("/practicals/{practical_id}/exam/heartbeat", response_model=ExamState)
async def exam_heartbeat(practical_id: str, body: ExamSessionBody, user: StudentUser, svc: Svc, request: Request):
    p = await _exam_practical(svc, user, practical_id, request)
    a = await exam.heartbeat(svc.repo, p, user, body.session_id)
    return await _exam_state(svc, request, p, user, body.session_id, a)


@router.post("/practicals/{practical_id}/exam/pause", response_model=ExamState)
async def exam_pause(practical_id: str, body: ExamSessionBody, user: StudentUser, svc: Svc, request: Request):
    """Pause button: a declared break (limited in number and length) that doesn't lock the exam."""
    p = await _exam_practical(svc, user, practical_id, request)
    a = await exam.pause(svc.repo, p, user, body.session_id)
    return await _exam_state(svc, request, p, user, body.session_id, a)


@router.post("/practicals/{practical_id}/exam/resume", response_model=ExamState)
async def exam_resume(practical_id: str, body: ExamSessionBody, user: StudentUser, svc: Svc, request: Request):
    """End the break in this tab. A break that ran over the limit comes back locked."""
    p = await _exam_practical(svc, user, practical_id, request)
    a = await exam.resume(svc.repo, p, user, body.session_id)
    return await _exam_state(svc, request, p, user, body.session_id, a)


@router.post("/practicals/{practical_id}/exam/violation", response_model=ExamState)
async def exam_violation(practical_id: str, body: ExamViolationBody, user: StudentUser, svc: Svc, request: Request):
    p, _ = await student_practical(svc, user, practical_id)  # no SEB check: violations must always be recordable
    if p.lockdown_mode == "off":
        raise HTTPException(status_code=409, detail="This practical does not use exam lockdown")
    a = await exam.violation(svc.repo, p, user, body.session_id, body.type, body.detail)
    return await _exam_state(svc, request, p, user, body.session_id, a)


@router.post("/practicals/{practical_id}/proctor/events", response_model=ProctorBatchResponse)
async def proctor_events(practical_id: str, body: ProctorBatch, user: StudentUser, svc: Svc):
    """Ingest proctoring telemetry. The baseline code of a session is captured server-side (never trusted
    from the client) so 'code that appeared without being typed' can be measured at submission."""
    p, _ = await student_practical(svc, user, practical_id)
    if not p.proctored:
        raise HTTPException(status_code=409, detail="This practical is not proctored")
    now = utcnow()
    session = await svc.repo.get_proctor_session(body.session_id)
    if session is None:
        draft = await svc.repo.get_draft(p.id, user.id)
        session = ProctorSessionRecord(
            id=body.session_id, practical_id=p.id, student_id=user.id,
            baseline_files=draft.files if draft else dict(p.starter_files), started_at=now, last_seen_at=now,
        )
    elif session.student_id != user.id or session.practical_id != p.id:
        raise HTTPException(status_code=409, detail="Invalid proctoring session")
    updated = await svc.repo.upsert_proctor_session(session.model_copy(update={
        "stats": body.stats.model_dump() if body.stats else session.stats, "last_seen_at": now,
    }))
    if updated is None:
        raise HTTPException(status_code=409, detail="Invalid proctoring session")

    records = []
    for ev in body.events:
        at = ev.at if (now - timedelta(days=1)) <= ev.at <= (now + timedelta(minutes=1)) else now
        detail = dict(ev.detail)
        if ev.type == "focus_lost":
            detail["duration_ms"] = max(0, min(int(detail.get("duration_ms", 0) or 0), 6 * 3600 * 1000))
        records.append(ProctorEventRecord(practical_id=p.id, student_id=user.id, session_id=updated.id,
                                          event_type=ev.type, detail=detail, occurred_at=at, created_at=now))
    await svc.repo.create_proctor_events(records)
    summary = proctor_summary(await svc.repo.list_proctor_sessions(p.id, user.id),
                              await svc.repo.list_proctor_events(p.id, user.id))
    return ProctorBatchResponse(accepted=len(records), summary=ProctorSummary(**summary))


@router.put("/practicals/{practical_id}/draft", response_model=DraftSaved)
async def save_draft(practical_id: str, body: FilesBody, user: StudentUser, svc: Svc, request: Request):
    p, _ = await student_practical(svc, user, practical_id)
    await exam.enforce(svc.repo, request, p, user, request.app.state.settings)
    rec = await svc.repo.upsert_draft(DraftRecord(practical_id=p.id, student_id=user.id, files=body.files))
    return DraftSaved(saved_at=rec.updated_at)


@router.post("/practicals/{practical_id}/run", response_model=ExecutionResult)
async def run(practical_id: str, body: RunRequest, user: StudentUser, svc: Svc, request: Request):
    p, _ = await student_practical(svc, user, practical_id)
    await exam.enforce(svc.repo, request, p, user, request.app.state.settings)
    visible = [t for t in p.test_cases if not t.hidden]
    result = await _execute(svc, ExecutionRequest(lab_type=p.lab_type, files=body.files, mode=body.mode, tests=visible))
    log = await svc.repo.create_execution_log(
        ExecutionLogRecord(
            practical_id=p.id, student_id=user.id, lab_type=p.lab_type, mode=body.mode, engine=result.engine,
            status=result.status, files=body.files, stdout=result.stdout[:20_000], stderr=result.stderr[:20_000],
            test_results=result.tests, tests_passed=result.tests_passed, tests_total=result.tests_total,
            duration_ms=result.duration_ms,
        )
    )
    await svc.repo.upsert_draft(DraftRecord(practical_id=p.id, student_id=user.id, files=body.files))
    result.execution_id = log.id
    return result


@router.post("/practicals/{practical_id}/lint", response_model=LintResponse)
async def lint(practical_id: str, body: LintRequest, user: StudentUser, svc: Svc, request: Request):
    p, _ = await student_practical(svc, user, practical_id)
    await exam.enforce(svc.repo, request, p, user, request.app.state.settings)
    filename = body.filename or LAB_FILENAME[p.lab_type]
    if filename not in body.files:
        raise HTTPException(status_code=422, detail=f"file '{filename}' not provided")
    return await svc.linter.lint(p.lab_type, filename, body.files[filename])


@router.post("/practicals/{practical_id}/hint", response_model=HintResponse)
async def hint(practical_id: str, body: HintRequest, user: StudentUser, svc: Svc, request: Request):
    p, _ = await student_practical(svc, user, practical_id)
    await exam.enforce(svc.repo, request, p, user, request.app.state.settings)
    execution = await svc.repo.get_latest_execution(p.id, user.id, mode="test")
    previous = await svc.repo.list_hint_logs(practical_ids=[p.id], student_id=user.id)
    resp = await svc.tutor.hint(practical=p, execution=execution, previous=previous, question=body.question)
    if (rec := svc.tutor.log_record(p.id, user.id, execution, resp, body.question)) is not None:
        await svc.repo.create_hint_log(rec)
    return resp


async def _integrity(svc: Svc, p: PracticalRecord, user: UserRecord, files: dict[str, str]):
    sessions = await svc.repo.list_proctor_sessions(p.id, user.id)
    events = await svc.repo.list_proctor_events(p.id, user.id)
    # classmates' latest submissions (synthetic seed data is excluded from comparisons with live work)
    peers_raw = [
        s for s in await svc.repo.list_submissions(practical_ids=[p.id])
        if s.student_id != user.id and s.grading_model != SEED_MODEL
    ]
    latest: dict[str, SubmissionRecord] = {}
    for s in peers_raw:  # newest first
        latest.setdefault(s.student_id, s)
    names = await svc.repo.get_users(list(latest))
    peers = [(s.id, names[sid].full_name if sid in names else "another student", s.files) for sid, s in latest.items()]
    # style references: starter, the code at the first proctored session, the student's other submissions
    refs = [code_text(p.lab_type, p.starter_files)]
    if sessions and sessions[0].baseline_files:
        refs.append(code_text(p.lab_type, sessions[0].baseline_files))
    for s in (await svc.repo.list_submissions(student_id=user.id))[:6]:
        if s.practical_id != p.id and LAB_FILENAME[p.lab_type] in s.files:
            refs.append(code_text(p.lab_type, s.files))
    return await svc.integrity.analyze(practical=p, files=files, sessions=sessions, events=events, peers=peers,
                                       reference_texts=refs[:4])


@router.post("/practicals/{practical_id}/submit", response_model=SubmissionOut)
async def submit(practical_id: str, body: FilesBody, user: StudentUser, svc: Svc, request: Request):
    p, course = await student_practical(svc, user, practical_id)
    await exam.enforce(svc.repo, request, p, user, request.app.state.settings)
    previous = await svc.repo.list_submissions(practical_ids=[p.id], student_id=user.id)
    if len(previous) >= MAX_SUBMISSIONS_PER_PRACTICAL:
        raise HTTPException(status_code=429, detail=f"Submission limit reached ({MAX_SUBMISSIONS_PER_PRACTICAL})")

    result = await _execute(svc, ExecutionRequest(lab_type=p.lab_type, files=body.files, mode="test", tests=p.test_cases))
    grade, integrity = await asyncio.gather(
        svc.grader.grade(p, body.files, result),
        _integrity(svc, p, user, body.files),
    )
    now = utcnow()
    sub = await svc.repo.create_submission(
        SubmissionRecord(
            practical_id=p.id, student_id=user.id, files=body.files, status="graded",
            tests_passed=result.tests_passed, tests_total=result.tests_total, test_results=result.tests,
            rubric_score=grade.total, max_score=p.max_score, rubric_breakdown=grade.breakdown,
            ai_feedback=grade.summary, grading_model=grade.model, integrity=integrity,
            submitted_at=now, graded_at=utcnow(),
        )
    )
    await svc.repo.upsert_draft(DraftRecord(practical_id=p.id, student_id=user.id, files=body.files))
    if p.lockdown_mode != "off":
        await exam.mark_submitted(svc.repo, p, user)
    return (await submissions_out(svc.repo, [sub], {p.id: p}, {course.id: course}))[0]


@router.get("/submissions", response_model=list[SubmissionOut])
async def my_submissions(user: StudentUser, svc: Svc):
    return await submissions_out(svc.repo, await svc.repo.list_submissions(student_id=user.id))
