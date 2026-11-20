"""Exam lockdown: server-side state machine, Safe Exam Browser verification and the live monitor.

Browsers cannot close a student's other tabs or apps, so the *web* exam mode enforces lockdown on the
server instead:

* exactly one browser tab (the "active session") may work on an exam — a second tab, a reload or
  navigating away locks the exam;
* the client reports focus loss / fullscreen exit / devtools as violations — the exam locks immediately;
* while locked (or from any other tab) the server refuses run / lint / hint / draft / submit;
* only a mentor (faculty / HOD) can unlock, from the Live Lab Monitor.

For a true OS-level lockdown, practicals can require **Safe Exam Browser** (lockdown_mode="seb"):
the server verifies the SEB Config Key hash — SHA-256 hex of (absolute URL without fragment + Config Key) —
either from the native `X-SafeExamBrowser-ConfigKeyHash` header or from the page-level JavaScript API value
`SafeExamBrowser.security.configKey` forwarded by our frontend (needed where SEB's modern WebView doesn't
send the header). Ref: https://safeexambrowser.org/developer/seb-config-key.html
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.config import Settings
from app.db.base import Repository
from app.models import (
    DraftRecord,
    ExamAttemptRecord,
    PracticalRecord,
    ProctorEventRecord,
    ProctorSessionRecord,
    UserRecord,
    utcnow,
)

MAX_BREAKS = 2  # Pause button: declared breaks per exam
BREAK_LIMIT = timedelta(minutes=10)  # a break that runs longer locks the exam
LIVE_WINDOW = timedelta(seconds=20)  # a session counts as "still open" if it heart-beat within this window
ONLINE_WINDOW = timedelta(seconds=30)

VIOLATION_REASONS = {
    "focus_lost": "Left the exam window (switched tab or app)",
    "fullscreen_exit": "Exited fullscreen",
    "devtools_blocked": "Tried to open developer tools",
    "second_tab": "Opened the exam in a second tab or window",
    "page_closed": "Left the exam page (closed, reloaded or navigated away)",
}
SEB_HEADER = "x-safeexambrowser-configkeyhash"
SEB_JS_HASH_HEADER = "x-seb-configkey-hash"
SEB_PAGE_URL_HEADER = "x-seb-page-url"
EXAM_SESSION_HEADER = "x-exam-session"


# ---------------------------------------------------------------- Safe Exam Browser
def seb_hash(url: str, config_key: str) -> str:
    return hashlib.sha256((url.split("#", 1)[0] + config_key).encode("utf-8")).hexdigest()


def seb_launch_url(config_url: str | None) -> str | None:
    """https://host/x.seb -> sebs://host/x.seb ; http -> seb:// (SEB's custom URL schemes)."""
    if not config_url:
        return None
    if config_url.startswith("https://"):
        return "sebs://" + config_url[len("https://"):]
    if config_url.startswith("http://"):
        return "seb://" + config_url[len("http://"):]
    return config_url


def seb_verified(request: Request, p: PracticalRecord, settings: Settings) -> bool:
    key = (p.seb_config_key or "").strip().lower()
    if not key:
        return False
    # 1) page-level JS API value forwarded by our frontend; must be for THIS practical's lab page on our origin
    page_url, js_hash = request.headers.get(SEB_PAGE_URL_HEADER), request.headers.get(SEB_JS_HASH_HEADER)
    if page_url and js_hash:
        parts = urlsplit(page_url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if (origin in settings.cors_origin_list and parts.path.rstrip("/").endswith(f"/student/labs/{p.id}")
                and hmac.compare_digest(seb_hash(page_url, key), js_hash.strip().lower())):
            return True
    # 2) native request header (classic WebView): hash of the API request URL itself
    native = request.headers.get(SEB_HEADER)
    if native and hmac.compare_digest(seb_hash(str(request.url), key), native.strip().lower()):
        return True
    return False


# ---------------------------------------------------------------- state machine
def _lock(a: ExamAttemptRecord, reason: str, now: datetime) -> None:
    a.status = "locked"
    a.lock_reason = reason
    a.locked_at = now


def _end_break(a: ExamAttemptRecord, now: datetime) -> int:
    """Close the current break; returns its length in ms."""
    ms = int((now - a.paused_at).total_seconds() * 1000) if a.paused_at else 0
    a.break_ms += ms
    a.paused_at = None
    return ms


async def _expire_break(repo: Repository, a: ExamAttemptRecord | None) -> ExamAttemptRecord | None:
    """A break that ran past BREAK_LIMIT locks the exam (checked lazily whenever the attempt is read)."""
    if a is None or a.status != "paused" or a.paused_at is None:
        return a
    now = utcnow()
    if now - a.paused_at <= BREAK_LIMIT:
        return a
    over_at = a.paused_at + BREAK_LIMIT
    _end_break(a, over_at)
    reason = f"Break ran over the {int(BREAK_LIMIT.total_seconds() // 60)}-minute limit"
    _lock(a, reason, over_at)
    a.violations += 1
    await _event(repo, a, "exam_locked", over_at, reason=reason, trigger="break_overrun")
    return await repo.save_exam_attempt(a)


async def load_attempt(repo: Repository, practical_id: str, student_id: str) -> ExamAttemptRecord | None:
    return await _expire_break(repo, await repo.get_exam_attempt(practical_id, student_id))


async def _event(repo: Repository, a: ExamAttemptRecord, kind: str, now: datetime, **detail) -> None:
    sid = a.active_session_id or a.last_session_id
    if sid is None:
        return
    await repo.create_proctor_events([ProctorEventRecord(
        practical_id=a.practical_id, student_id=a.student_id, session_id=sid, event_type=kind,
        detail=detail, occurred_at=now, created_at=now,
    )])


async def _ensure_proctor_session(repo: Repository, p: PracticalRecord, user: UserRecord, session_id: str,
                                  now: datetime) -> None:
    """The exam tab is also a proctoring session; capture its baseline code server-side."""
    existing = await repo.get_proctor_session(session_id)
    if existing is None:
        draft: DraftRecord | None = await repo.get_draft(p.id, user.id)
        await repo.upsert_proctor_session(ProctorSessionRecord(
            id=session_id, practical_id=p.id, student_id=user.id,
            baseline_files=draft.files if draft else dict(p.starter_files), started_at=now, last_seen_at=now,
        ))
    elif existing.student_id != user.id or existing.practical_id != p.id:
        raise HTTPException(status_code=409, detail="Invalid exam session")


async def start(repo: Repository, p: PracticalRecord, user: UserRecord, session_id: str) -> ExamAttemptRecord:
    now = utcnow()
    a = await load_attempt(repo, p.id, user.id)
    if a is None:
        await _ensure_proctor_session(repo, p, user, session_id, now)
        a = ExamAttemptRecord(practical_id=p.id, student_id=user.id, active_session_id=session_id,
                              last_session_id=session_id, started_at=now, last_heartbeat_at=now)
        return await repo.save_exam_attempt(a)
    if a.status != "active":
        return a
    if a.active_session_id in (None, session_id):  # first tab, same tab, or resuming after a mentor unlock
        await _ensure_proctor_session(repo, p, user, session_id, now)
        a.active_session_id, a.last_session_id, a.last_heartbeat_at = session_id, session_id, now
        return await repo.save_exam_attempt(a)
    # a different tab/window while the exam is active
    still_open = a.last_heartbeat_at is not None and now - a.last_heartbeat_at < LIVE_WINDOW
    reason = (VIOLATION_REASONS["second_tab"] if still_open
              else "Exam session was interrupted (page closed, reloaded or navigated away)")
    _lock(a, reason, now)
    a.violations += 1
    await _event(repo, a, "exam_locked", now, reason=reason)
    return await repo.save_exam_attempt(a)


async def heartbeat(repo: Repository, p: PracticalRecord, user: UserRecord, session_id: str) -> ExamAttemptRecord | None:
    a = await load_attempt(repo, p.id, user.id)
    if a is not None and a.status == "active" and a.active_session_id == session_id:
        a.last_heartbeat_at = utcnow()
        a = await repo.save_exam_attempt(a)
    return a


async def pause(repo: Repository, p: PracticalRecord, user: UserRecord, session_id: str) -> ExamAttemptRecord:
    """Start a declared break from the tab holding the exam. Leaving, closing the tab or exiting fullscreen during
    the break is not a violation; the work stays inaccessible until the student resumes."""
    a = await load_attempt(repo, p.id, user.id)
    if a is None or a.status != "active" or a.active_session_id != session_id:
        raise HTTPException(status_code=409, detail="Only the tab holding an active exam can pause it")
    if a.breaks_used >= MAX_BREAKS:
        raise HTTPException(status_code=409, detail=f"You have used all {MAX_BREAKS} breaks for this exam")
    now = utcnow()
    a.breaks_used += 1
    await _event(repo, a, "break_start", now, break_number=a.breaks_used)
    a.status, a.paused_at, a.active_session_id, a.last_heartbeat_at = "paused", now, None, now
    return await repo.save_exam_attempt(a)


async def resume(repo: Repository, p: PracticalRecord, user: UserRecord, session_id: str) -> ExamAttemptRecord:
    """End the break and claim the exam for this tab (the student may have closed the old one during the break)."""
    a = await load_attempt(repo, p.id, user.id)  # an overrun break is already locked here
    if a is None or a.status != "paused":
        if a is not None and a.status in ("locked", "submitted"):
            return a
        raise HTTPException(status_code=409, detail="This exam is not paused")
    now = utcnow()
    await _ensure_proctor_session(repo, p, user, session_id, now)
    ms = _end_break(a, now)
    a.status, a.active_session_id, a.last_session_id, a.last_heartbeat_at = "active", session_id, session_id, now
    await _event(repo, a, "break_end", now, duration_ms=ms, break_number=a.breaks_used)
    return await repo.save_exam_attempt(a)


async def violation(repo: Repository, p: PracticalRecord, user: UserRecord, session_id: str, kind: str,
                    detail: str | None) -> ExamAttemptRecord | None:
    a = await load_attempt(repo, p.id, user.id)
    if a is None or a.status == "submitted":
        return a
    if a.status != "active" or a.active_session_id != session_id:
        return a  # only the tab holding the exam can lock it (already locked / stale tab: nothing to count)
    now = utcnow()
    a.violations += 1
    reason = VIOLATION_REASONS.get(kind, "Exam rule violation")
    _lock(a, reason, now)
    await _event(repo, a, "exam_locked", now, reason=reason, trigger=kind, **({"detail": detail} if detail else {}))
    return await repo.save_exam_attempt(a)


async def unlock(repo: Repository, p: PracticalRecord, student_id: str, mentor: UserRecord) -> ExamAttemptRecord:
    a = await load_attempt(repo, p.id, student_id)
    if a is None or a.status != "locked":
        raise HTTPException(status_code=409, detail="This student's exam is not locked")
    now = utcnow()
    await _event(repo, a, "exam_unlocked", now, by=mentor.full_name, previous_reason=a.lock_reason or "")
    a.status, a.active_session_id, a.lock_reason = "active", None, None
    a.unlock_count += 1
    a.unlocked_at, a.unlocked_by = now, mentor.id
    return await repo.save_exam_attempt(a)


async def mentor_lock(repo: Repository, p: PracticalRecord, student_id: str, mentor: UserRecord,
                      reason: str | None) -> ExamAttemptRecord:
    a = await load_attempt(repo, p.id, student_id)
    if a is None or a.status not in ("active", "paused"):
        raise HTTPException(status_code=409, detail="This student's exam is not active")
    now = utcnow()
    if a.status == "paused":
        _end_break(a, now)
    text = f"Locked by {mentor.full_name}" + (f": {reason}" if reason else "")
    _lock(a, text, now)
    await _event(repo, a, "exam_locked", now, reason=text, by=mentor.full_name)
    return await repo.save_exam_attempt(a)


async def mark_submitted(repo: Repository, p: PracticalRecord, user: UserRecord) -> None:
    a = await load_attempt(repo, p.id, user.id)
    if a is not None:
        a.status, a.submitted_at, a.active_session_id = "submitted", utcnow(), None
        await repo.save_exam_attempt(a)


async def enforce(repo: Repository, request: Request, p: PracticalRecord, user: UserRecord, settings: Settings) -> None:
    """Gate for every write-ish student action on a lockdown practical."""
    if p.lockdown_mode == "off":
        return
    if p.lockdown_mode == "seb" and not seb_verified(request, p, settings):
        raise HTTPException(status_code=403, detail="This exam must be taken in Safe Exam Browser")
    a = await load_attempt(repo, p.id, user.id)
    session_id = request.headers.get(EXAM_SESSION_HEADER)
    if a is None:
        raise HTTPException(status_code=409, detail="Start the exam session first")
    if a.status == "submitted":
        raise HTTPException(status_code=409, detail="This exam has already been submitted")
    if a.status == "locked":
        raise HTTPException(status_code=423, detail=f"Exam locked: {a.lock_reason}. Ask your mentor to unlock it.")
    if a.status == "paused":
        raise HTTPException(status_code=423, detail="Your exam is paused. Resume it to continue.")
    if not session_id or a.active_session_id != session_id:
        raise HTTPException(status_code=409, detail="This exam is active in another tab or window")
    a.last_heartbeat_at = utcnow()
    await repo.save_exam_attempt(a)


def exam_state(p: PracticalRecord, a: ExamAttemptRecord | None, session_id: str | None, seb_ok: bool) -> dict:
    return {
        "lockdown_mode": p.lockdown_mode,
        "status": a.status if a else "not_started",
        "lock_reason": a.lock_reason if a else None,
        "violations": a.violations if a else 0,
        "locked_at": a.locked_at if a else None,
        "is_current_session": bool(a and session_id and a.active_session_id == session_id),
        "awaiting_resume": bool(a and a.status == "active" and a.active_session_id is None),
        "seb_required": p.lockdown_mode == "seb",
        "seb_verified": seb_ok,
        "paused_at": a.paused_at if a else None,
        "breaks_used": a.breaks_used if a else 0,
        "max_breaks": MAX_BREAKS,
        "break_limit_s": int(BREAK_LIMIT.total_seconds()),
    }


# ---------------------------------------------------------------- live monitor
async def monitor_rows(repo: Repository, p: PracticalRecord) -> list[dict]:
    now = utcnow()
    enrolled = (await repo.list_enrollments([p.course_id])).get(p.course_id, [])
    users = await repo.get_users(enrolled)
    attempts = {a.student_id: await _expire_break(repo, a) for a in await repo.list_exam_attempts([p.id])}
    all_sessions = await repo.list_practical_proctor_sessions(p.id)
    sessions: dict[str, list[ProctorSessionRecord]] = {}
    for s in all_sessions:
        sessions.setdefault(s.student_id, []).append(s)
    # polled every few seconds: the repository avoids re-reading what can't have changed
    tallies = await repo.practical_proctor_tallies(p.id, all_sessions)
    latest_exec = await repo.latest_test_runs(p.id)
    subs = await repo.latest_submissions(p.id)

    rows = []
    for sid in enrolled:
        u = users.get(sid)
        if u is None:
            continue
        a, t, ss = attempts.get(sid), tallies.get(sid, {}), sessions.get(sid, [])
        seen = [t for t in ([a.last_heartbeat_at] if a and a.last_heartbeat_at else []) + [s.last_seen_at for s in ss] if t]
        last_seen = max(seen) if seen else None
        sub = subs.get(sid)
        if a is not None:
            status = a.status
        elif sub is not None:
            status = "submitted"
        elif ss:
            status = "active"
        else:
            status = "not_started"

        ex = latest_exec.get(sid)
        rows.append({
            "student_id": sid, "student_name": u.full_name, "roll_number": u.roll_number,
            "status": status,
            "online": bool(last_seen and now - last_seen < ONLINE_WINDOW and status in ("active", "paused")),
            "last_seen_at": last_seen, "lock_reason": a.lock_reason if a else None,
            "locked_at": a.locked_at if a else None, "violations": a.violations if a else 0,
            "unlock_count": a.unlock_count if a else 0,
            "paste_blocked": t.get("paste_blocked", 0), "copy_blocked": t.get("copy_blocked", 0),
            "focus_lost": t.get("focus_lost", 0), "fullscreen_exits": t.get("fullscreen_exits", 0),
            "time_away_ms": t.get("time_away_ms", 0),
            "tests_passed": ex.tests_passed if ex else None, "tests_total": ex.tests_total if ex else None,
            "submission_id": sub.id if sub else None, "final_score": sub.final_score if sub else None,
            "max_score": p.max_score,
            "integrity_risk": sub.integrity.risk_level if sub and sub.integrity else None,
            "paused_at": a.paused_at if a and a.status == "paused" else None,
            "breaks_used": a.breaks_used if a else t.get("breaks", 0),
            "break_ms": a.break_ms if a else t.get("break_ms", 0),
        })
    order = {"locked": 0, "paused": 1, "active": 1, "not_started": 2, "submitted": 3}
    rows.sort(key=lambda r: (order.get(r["status"], 9), not r["online"], r["student_name"]))
    return rows
