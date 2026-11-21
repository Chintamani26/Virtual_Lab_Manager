"""AI Lab Tutor endpoints (docs/API.md v1.5).

Students: GET/POST /api/student/practicals/{id}/tutor. Same access rules as the rest of the lab: enrolled students
only, published practicals, exam lockdown enforced on POST. The conversation lives server-side; the browser only
sends the new message or quick action.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

from app.deps import Svc, student_practical
from app.models import DraftRecord, ExecutionLogRecord, PracticalRecord, TutorThreadRecord, utcnow
from app.schemas import TutorReplyOut, TutorRequest, TutorThreadOut, TutorTranscriptOut
from app.security import StudentUser
from app.services import exam

router = APIRouter(prefix="/api/student", tags=["tutor"])

PER_MINUTE = 8   # tutor requests per student per practical
PER_DAY = 60
GUARD_FLAGS = {"injection", "restricted", "solution_request"}


def _student_times(thread: TutorThreadRecord | None) -> list[datetime]:
    return [m.created_at for m in thread.messages if m.role == "student"] if thread else []


def remaining_today(thread: TutorThreadRecord | None, now: datetime) -> int:
    used = sum(1 for t in _student_times(thread) if t > now - timedelta(days=1))
    return max(0, PER_DAY - used)


def check_rate(thread: TutorThreadRecord | None, now: datetime) -> None:
    times = _student_times(thread)
    if sum(1 for t in times if t > now - timedelta(minutes=1)) >= PER_MINUTE:
        raise HTTPException(status_code=429, detail="Slow down a little: wait a minute before asking the tutor again.")
    if remaining_today(thread, now) == 0:
        raise HTTPException(status_code=429, detail=f"You've used today's {PER_DAY} tutor questions for this lab. "
                                                    "Try again tomorrow, or ask your teacher.")


def current_files(p: PracticalRecord, draft: DraftRecord | None,
                  execution: ExecutionLogRecord | None) -> tuple[dict[str, str], bool]:
    """The student's latest files, and whether they changed after the last test run (results may be stale)."""
    if execution is None:
        return (draft.files if draft else dict(p.starter_files)), False
    if draft and draft.updated_at > execution.created_at and draft.files != execution.files:
        return draft.files, True
    return execution.files, False


@router.get("/practicals/{practical_id}/tutor", response_model=TutorThreadOut)
async def tutor_history(practical_id: str, user: StudentUser, svc: Svc):
    p, _ = await student_practical(svc, user, practical_id)
    thread = await svc.repo.get_tutor_thread(p.id, user.id)
    return TutorThreadOut(
        messages=thread.messages if thread else [], dropped=thread.dropped if thread else 0,
        ai_enabled=svc.ai.enabled, remaining_today=remaining_today(thread, utcnow()), per_day=PER_DAY,
    )


@router.post("/practicals/{practical_id}/tutor", response_model=TutorReplyOut)
async def tutor_message(practical_id: str, body: TutorRequest, user: StudentUser, svc: Svc, request: Request):
    p, _ = await student_practical(svc, user, practical_id)
    await exam.enforce(svc.repo, request, p, user, request.app.state.settings)
    if body.action == "chat" and not (body.message or "").strip():
        raise HTTPException(status_code=422, detail="Type a question first")
    thread = await svc.repo.get_tutor_thread(p.id, user.id)
    check_rate(thread, utcnow())

    execution = await svc.repo.get_latest_execution(p.id, user.id, mode="test")
    files, stale = current_files(p, await svc.repo.get_draft(p.id, user.id), execution)
    previous = (await svc.repo.list_hint_logs(practical_ids=[p.id], student_id=user.id)
                if body.action == "next_hint" else [])
    turn = await svc.lab_tutor.respond(
        practical=p, files=files, execution=execution, results_stale=stale, thread=thread,
        previous_hints=previous, action=body.action, message=body.message, test=body.test,
    )
    if turn.hint is not None:
        question = turn.student.content if (body.message or "").strip() else None
        if (rec := svc.tutor.log_record(p.id, user.id, execution, turn.hint, question)) is not None:
            await svc.repo.create_hint_log(rec)
    thread = await svc.repo.append_tutor_messages(p.id, user.id, [turn.student, turn.tutor])
    return TutorReplyOut(messages=[turn.student, turn.tutor], remaining_today=remaining_today(thread, utcnow()))


def transcript_out(thread: TutorThreadRecord | None) -> TutorTranscriptOut:
    msgs = thread.messages if thread else []
    hints = [m for m in msgs if m.role == "tutor" and m.action == "next_hint" and m.hint_level]
    return TutorTranscriptOut(
        messages=msgs, dropped=thread.dropped if thread else 0,
        student_messages=sum(1 for m in msgs if m.role == "student"),
        hints=len(hints), max_hint_level=max((m.hint_level or 0 for m in hints), default=0),
        flagged=sum(1 for m in msgs if m.role == "student" and GUARD_FLAGS & set(m.flags)),
        concept_checks=[m.understanding for m in msgs if m.role == "tutor" and m.understanding],
    )
