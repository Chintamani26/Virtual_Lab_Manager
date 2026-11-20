"""Repository interface. Two implementations: in-memory (demo) and PostgreSQL (AlloyDB/Supabase)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.models import (
    CourseRecord,
    Department,
    DraftRecord,
    ExamAttemptRecord,
    ExecutionLogRecord,
    HintLogRecord,
    PracticalRecord,
    ProctorEventRecord,
    ProctorSessionRecord,
    Role,
    SubmissionRecord,
    TutorMessage,
    TutorThreadRecord,
    UserRecord,
)

# Messages kept per tutor thread (oldest dropped first). Each message is capped (app/ai/tutor_chat.py), so a
# thread stays a few hundred KB at most, far below Firestore's 1 MiB document limit.
TUTOR_THREAD_LIMIT = 200


def tally_event(t: dict[str, int], e: ProctorEventRecord) -> None:
    """Add one proctoring event to per-student totals shown on the Live Lab Monitor."""
    kind = e.event_type
    duration = int(e.detail.get("duration_ms", 0) or 0)
    key = {"paste_blocked": "paste_blocked", "copy_blocked": "copy_blocked", "cut_blocked": "copy_blocked",
           "focus_lost": "focus_lost", "fullscreen_exit": "fullscreen_exits", "break_start": "breaks"}.get(kind)
    if key:
        t[key] = t.get(key, 0) + 1
    if kind == "focus_lost":
        t["time_away_ms"] = t.get("time_away_ms", 0) + duration
    elif kind == "break_end":
        t["break_ms"] = t.get("break_ms", 0) + duration


def merge_tally(into: dict[str, int], t: dict[str, int]) -> None:
    for k, v in t.items():
        into[k] = into.get(k, 0) + v


class Repository(ABC):
    name: str = "abstract"

    async def connect(self) -> None:  # pragma: no cover - optional hook
        return None

    async def close(self) -> None:  # pragma: no cover - optional hook
        return None

    # ---- departments / users
    @abstractmethod
    async def get_department(self, department_id: str) -> Department | None: ...

    @abstractmethod
    async def get_user(self, user_id: str) -> UserRecord | None: ...

    @abstractmethod
    async def get_user_by_email(self, email: str) -> UserRecord | None: ...

    @abstractmethod
    async def list_users(self, department_id: str, role: Role | None = None) -> list[UserRecord]: ...

    @abstractmethod
    async def get_users(self, user_ids: list[str]) -> dict[str, UserRecord]: ...

    # ---- courses / enrollments
    @abstractmethod
    async def get_course(self, course_id: str) -> CourseRecord | None: ...

    @abstractmethod
    async def list_courses(
        self,
        *,
        department_id: str | None = None,
        faculty_id: str | None = None,
        student_id: str | None = None,
    ) -> list[CourseRecord]: ...

    @abstractmethod
    async def set_course_faculty(self, course_id: str, faculty_id: str) -> CourseRecord: ...

    @abstractmethod
    async def list_enrollments(self, course_ids: list[str]) -> dict[str, list[str]]:
        """course_id -> [student_id, ...]"""

    async def is_enrolled(self, course_id: str, student_id: str) -> bool:
        """Access check on every student request. Stores that bill per document read override this."""
        return student_id in (await self.list_enrollments([course_id])).get(course_id, [])

    # ---- practicals
    @abstractmethod
    async def get_practical(self, practical_id: str) -> PracticalRecord | None: ...

    @abstractmethod
    async def list_practicals(self, course_ids: list[str], published_only: bool = False) -> list[PracticalRecord]: ...

    @abstractmethod
    async def create_practical(self, rec: PracticalRecord) -> PracticalRecord: ...

    @abstractmethod
    async def update_practical(self, rec: PracticalRecord) -> PracticalRecord: ...

    # ---- drafts
    @abstractmethod
    async def get_draft(self, practical_id: str, student_id: str) -> DraftRecord | None: ...

    @abstractmethod
    async def upsert_draft(self, rec: DraftRecord) -> DraftRecord: ...

    # ---- submissions
    @abstractmethod
    async def create_submission(self, rec: SubmissionRecord) -> SubmissionRecord: ...

    @abstractmethod
    async def update_submission(self, rec: SubmissionRecord) -> SubmissionRecord: ...

    @abstractmethod
    async def get_submission(self, submission_id: str) -> SubmissionRecord | None: ...

    @abstractmethod
    async def list_submissions(
        self, *, practical_ids: list[str] | None = None, student_id: str | None = None
    ) -> list[SubmissionRecord]:
        """Newest first."""

    # ---- execution logs
    @abstractmethod
    async def create_execution_log(self, rec: ExecutionLogRecord) -> ExecutionLogRecord: ...

    @abstractmethod
    async def get_latest_execution(
        self, practical_id: str, student_id: str, mode: str = "test"
    ) -> ExecutionLogRecord | None: ...

    @abstractmethod
    async def list_execution_logs(
        self, practical_ids: list[str], since: datetime | None = None
    ) -> list[ExecutionLogRecord]:
        """Lightweight listing for analytics: `files`, `stdout`, `stderr` may be empty."""

    async def list_student_execution_logs(self, student_id: str, practical_ids: list[str]) -> list[ExecutionLogRecord]:
        """One student's runs on these practicals (lightweight, like list_execution_logs)."""
        if not practical_ids:
            return []
        return [e for e in await self.list_execution_logs(practical_ids) if e.student_id == student_id]

    async def latest_submissions(self, practical_id: str) -> dict[str, SubmissionRecord]:
        """student_id -> newest submission on this practical (Live Lab Monitor, polled)."""
        latest: dict[str, SubmissionRecord] = {}
        for s in await self.list_submissions(practical_ids=[practical_id]):  # newest first
            latest.setdefault(s.student_id, s)
        return latest

    async def practical_proctor_tallies(
        self, practical_id: str, sessions: list[ProctorSessionRecord]
    ) -> dict[str, dict[str, int]]:
        """student_id -> proctoring event totals (tally_event) for the Live Lab Monitor.
        `sessions` are this practical's sessions, which a store may use to skip re-reading old events."""
        out: dict[str, dict[str, int]] = {}
        for e in await self.list_practical_proctor_events(practical_id):
            tally_event(out.setdefault(e.student_id, {}), e)
        return out

    async def latest_test_runs(self, practical_id: str) -> dict[str, ExecutionLogRecord]:
        """student_id -> newest test-mode run on this practical (Live Lab Monitor, polled)."""
        latest: dict[str, ExecutionLogRecord] = {}
        for e in sorted(await self.list_execution_logs([practical_id]), key=lambda e: e.created_at):
            if e.mode == "test":
                latest[e.student_id] = e
        return latest

    # ---- hints
    @abstractmethod
    async def create_hint_log(self, rec: HintLogRecord) -> HintLogRecord: ...

    @abstractmethod
    async def list_hint_logs(
        self, *, practical_ids: list[str] | None = None, student_id: str | None = None
    ) -> list[HintLogRecord]: ...

    # ---- AI Lab Tutor conversations
    @abstractmethod
    async def get_tutor_thread(self, practical_id: str, student_id: str) -> TutorThreadRecord | None: ...

    @abstractmethod
    async def append_tutor_messages(
        self, practical_id: str, student_id: str, messages: list[TutorMessage]
    ) -> TutorThreadRecord:
        """Append atomically (creating the thread if needed); keep the newest TUTOR_THREAD_LIMIT messages."""

    @abstractmethod
    async def list_tutor_threads(self, practical_ids: list[str]) -> list[TutorThreadRecord]:
        """Every student's thread on these practicals (learning-difficulty analysis)."""

    # ---- proctoring
    @abstractmethod
    async def create_proctor_events(self, events: list[ProctorEventRecord]) -> None: ...

    @abstractmethod
    async def list_proctor_events(self, practical_id: str, student_id: str) -> list[ProctorEventRecord]:
        """Oldest first."""

    @abstractmethod
    async def get_proctor_session(self, session_id: str) -> ProctorSessionRecord | None: ...

    @abstractmethod
    async def upsert_proctor_session(self, rec: ProctorSessionRecord) -> ProctorSessionRecord | None:
        """Insert, or update stats/last_seen_at. Returns None if the id belongs to another student/practical."""

    @abstractmethod
    async def list_proctor_sessions(self, practical_id: str, student_id: str) -> list[ProctorSessionRecord]:
        """Oldest first."""

    @abstractmethod
    async def list_practical_proctor_sessions(self, practical_id: str) -> list[ProctorSessionRecord]: ...

    @abstractmethod
    async def list_practical_proctor_events(self, practical_id: str) -> list[ProctorEventRecord]: ...

    # ---- exam lockdown
    @abstractmethod
    async def get_exam_attempt(self, practical_id: str, student_id: str) -> ExamAttemptRecord | None: ...

    @abstractmethod
    async def save_exam_attempt(self, rec: ExamAttemptRecord) -> ExamAttemptRecord:
        """Insert or fully update (unique per practical + student)."""

    @abstractmethod
    async def list_exam_attempts(self, practical_ids: list[str]) -> list[ExamAttemptRecord]: ...


def append_to_thread(thread: TutorThreadRecord | None, practical_id: str, student_id: str,
                     messages: list[TutorMessage]) -> TutorThreadRecord:
    """Shared append + trim used by every store."""
    t = thread.model_copy(deep=True) if thread else TutorThreadRecord(practical_id=practical_id, student_id=student_id)
    t.messages.extend(messages)
    extra = len(t.messages) - TUTOR_THREAD_LIMIT
    if extra > 0:
        t.messages = t.messages[extra:]
        t.dropped += extra
    t.updated_at = messages[-1].created_at if messages else t.updated_at
    return t
