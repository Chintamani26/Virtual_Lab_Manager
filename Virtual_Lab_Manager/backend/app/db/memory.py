"""In-memory repository used for demo mode, local development and tests.

State lives in process memory and resets on restart. On Cloud Run run a single instance
(--max-instances=1) when using this mode, or switch to PostgreSQL via DATABASE_URL.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.db.base import Repository, append_to_thread
from app.db.seed_data import SeedBundle
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


class MemoryRepository(Repository):
    name = "memory"

    def __init__(self, seed: SeedBundle | None = None) -> None:
        self._lock = asyncio.Lock()
        self.departments: dict[str, Department] = {}
        self.users: dict[str, UserRecord] = {}
        self.courses: dict[str, CourseRecord] = {}
        self.enrollments: dict[str, set[str]] = {}
        self.practicals: dict[str, PracticalRecord] = {}
        self.drafts: dict[tuple[str, str], DraftRecord] = {}
        self.submissions: dict[str, SubmissionRecord] = {}
        self.executions: list[ExecutionLogRecord] = []
        self.hints: list[HintLogRecord] = []
        self.proctor_events: list[ProctorEventRecord] = []
        self.proctor_sessions: dict[str, ProctorSessionRecord] = {}
        self.exam_attempts: dict[tuple[str, str], ExamAttemptRecord] = {}
        self.tutor_threads: dict[tuple[str, str], TutorThreadRecord] = {}
        if seed:
            self.load(seed)

    def load(self, seed: SeedBundle) -> None:
        for d in seed.departments:
            self.departments[d.id] = d
        for u in seed.users:
            self.users[u.id] = u
        for c in seed.courses:
            self.courses[c.id] = c
        for course_id, student_id in seed.enrollments:
            self.enrollments.setdefault(course_id, set()).add(student_id)
        for p in seed.practicals:
            self.practicals[p.id] = p
        for dr in seed.drafts:
            self.drafts[(dr.practical_id, dr.student_id)] = dr
        for s in seed.submissions:
            self.submissions[s.id] = s
        self.executions.extend(seed.execution_logs)
        self.hints.extend(seed.hint_logs)
        self.proctor_events.extend(seed.proctor_events)
        for ps in seed.proctor_sessions:
            self.proctor_sessions[ps.id] = ps

    # ---- departments / users
    async def get_department(self, department_id: str) -> Department | None:
        return self.departments.get(department_id)

    async def get_user(self, user_id: str) -> UserRecord | None:
        return self.users.get(user_id)

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        email = email.strip().lower()
        return next((u for u in self.users.values() if u.email.lower() == email), None)

    async def list_users(self, department_id: str, role: Role | None = None) -> list[UserRecord]:
        users = [u for u in self.users.values() if u.department_id == department_id and (role is None or u.role == role)]
        return sorted(users, key=lambda u: u.full_name)

    async def get_users(self, user_ids: list[str]) -> dict[str, UserRecord]:
        return {uid: self.users[uid] for uid in set(user_ids) if uid in self.users}

    # ---- courses
    async def get_course(self, course_id: str) -> CourseRecord | None:
        return self.courses.get(course_id)

    async def list_courses(self, *, department_id=None, faculty_id=None, student_id=None) -> list[CourseRecord]:
        out = []
        for c in self.courses.values():
            if department_id and c.department_id != department_id:
                continue
            if faculty_id and c.faculty_id != faculty_id:
                continue
            if student_id and student_id not in self.enrollments.get(c.id, set()):
                continue
            out.append(c)
        return sorted(out, key=lambda c: c.code)

    async def set_course_faculty(self, course_id: str, faculty_id: str) -> CourseRecord:
        async with self._lock:
            course = self.courses[course_id].model_copy(update={"faculty_id": faculty_id})
            self.courses[course_id] = course
            return course

    async def list_enrollments(self, course_ids: list[str]) -> dict[str, list[str]]:
        return {cid: sorted(self.enrollments.get(cid, set())) for cid in course_ids}

    # ---- practicals
    async def get_practical(self, practical_id: str) -> PracticalRecord | None:
        return self.practicals.get(practical_id)

    async def list_practicals(self, course_ids: list[str], published_only: bool = False) -> list[PracticalRecord]:
        ids = set(course_ids)
        out = [
            p
            for p in self.practicals.values()
            if p.course_id in ids and (not published_only or p.status == "published")
        ]
        return sorted(out, key=lambda p: (p.due_at is None, p.due_at or p.created_at, p.title))

    async def create_practical(self, rec: PracticalRecord) -> PracticalRecord:
        async with self._lock:
            self.practicals[rec.id] = rec
        return rec

    async def update_practical(self, rec: PracticalRecord) -> PracticalRecord:
        async with self._lock:
            self.practicals[rec.id] = rec
        return rec

    # ---- drafts
    async def get_draft(self, practical_id: str, student_id: str) -> DraftRecord | None:
        return self.drafts.get((practical_id, student_id))

    async def upsert_draft(self, rec: DraftRecord) -> DraftRecord:
        async with self._lock:
            self.drafts[(rec.practical_id, rec.student_id)] = rec
        return rec

    # ---- submissions
    async def create_submission(self, rec: SubmissionRecord) -> SubmissionRecord:
        async with self._lock:
            self.submissions[rec.id] = rec
        return rec

    async def update_submission(self, rec: SubmissionRecord) -> SubmissionRecord:
        async with self._lock:
            self.submissions[rec.id] = rec
        return rec

    async def get_submission(self, submission_id: str) -> SubmissionRecord | None:
        return self.submissions.get(submission_id)

    async def list_submissions(self, *, practical_ids=None, student_id=None) -> list[SubmissionRecord]:
        pids = set(practical_ids) if practical_ids is not None else None
        out = [
            s
            for s in self.submissions.values()
            if (pids is None or s.practical_id in pids) and (student_id is None or s.student_id == student_id)
        ]
        return sorted(out, key=lambda s: s.submitted_at, reverse=True)

    # ---- execution logs
    async def create_execution_log(self, rec: ExecutionLogRecord) -> ExecutionLogRecord:
        async with self._lock:
            self.executions.append(rec)
        return rec

    async def get_latest_execution(self, practical_id: str, student_id: str, mode: str = "test"):
        candidates = [
            e for e in self.executions if e.practical_id == practical_id and e.student_id == student_id and e.mode == mode
        ]
        return max(candidates, key=lambda e: e.created_at) if candidates else None

    async def list_execution_logs(self, practical_ids: list[str], since: datetime | None = None):
        pids = set(practical_ids)
        return [e for e in self.executions if e.practical_id in pids and (since is None or e.created_at >= since)]

    # ---- hints
    async def create_hint_log(self, rec: HintLogRecord) -> HintLogRecord:
        async with self._lock:
            self.hints.append(rec)
        return rec

    async def list_hint_logs(self, *, practical_ids=None, student_id=None) -> list[HintLogRecord]:
        pids = set(practical_ids) if practical_ids is not None else None
        return [
            h
            for h in self.hints
            if (pids is None or h.practical_id in pids) and (student_id is None or h.student_id == student_id)
        ]

    # ---- AI Lab Tutor conversations
    async def get_tutor_thread(self, practical_id: str, student_id: str) -> TutorThreadRecord | None:
        t = self.tutor_threads.get((practical_id, student_id))
        return t.model_copy(deep=True) if t else None

    async def append_tutor_messages(self, practical_id: str, student_id: str,
                                    messages: list[TutorMessage]) -> TutorThreadRecord:
        async with self._lock:
            key = (practical_id, student_id)
            self.tutor_threads[key] = append_to_thread(self.tutor_threads.get(key), practical_id, student_id, messages)
            return self.tutor_threads[key].model_copy(deep=True)

    async def list_tutor_threads(self, practical_ids: list[str]) -> list[TutorThreadRecord]:
        pids = set(practical_ids)
        return [t.model_copy(deep=True) for (pid, _), t in self.tutor_threads.items() if pid in pids]

    # ---- proctoring
    async def create_proctor_events(self, events: list[ProctorEventRecord]) -> None:
        async with self._lock:
            self.proctor_events.extend(events)

    async def list_proctor_events(self, practical_id: str, student_id: str) -> list[ProctorEventRecord]:
        out = [e for e in self.proctor_events if e.practical_id == practical_id and e.student_id == student_id]
        return sorted(out, key=lambda e: (e.occurred_at, e.created_at))

    async def get_proctor_session(self, session_id: str) -> ProctorSessionRecord | None:
        return self.proctor_sessions.get(session_id)

    async def upsert_proctor_session(self, rec: ProctorSessionRecord) -> ProctorSessionRecord | None:
        async with self._lock:
            cur = self.proctor_sessions.get(rec.id)
            if cur is None:
                self.proctor_sessions[rec.id] = rec
                return rec
            if cur.student_id != rec.student_id or cur.practical_id != rec.practical_id:
                return None
            cur = cur.model_copy(update={"stats": rec.stats, "last_seen_at": rec.last_seen_at})
            self.proctor_sessions[rec.id] = cur
            return cur

    async def list_proctor_sessions(self, practical_id: str, student_id: str) -> list[ProctorSessionRecord]:
        out = [s for s in self.proctor_sessions.values() if s.practical_id == practical_id and s.student_id == student_id]
        return sorted(out, key=lambda s: s.started_at)

    async def list_practical_proctor_sessions(self, practical_id: str) -> list[ProctorSessionRecord]:
        return sorted((s for s in self.proctor_sessions.values() if s.practical_id == practical_id),
                      key=lambda s: s.started_at)

    async def list_practical_proctor_events(self, practical_id: str) -> list[ProctorEventRecord]:
        return sorted((e for e in self.proctor_events if e.practical_id == practical_id), key=lambda e: e.occurred_at)

    # ---- exam lockdown
    async def get_exam_attempt(self, practical_id: str, student_id: str) -> ExamAttemptRecord | None:
        return self.exam_attempts.get((practical_id, student_id))

    async def save_exam_attempt(self, rec: ExamAttemptRecord) -> ExamAttemptRecord:
        async with self._lock:
            self.exam_attempts[(rec.practical_id, rec.student_id)] = rec
        return rec

    async def list_exam_attempts(self, practical_ids: list[str]) -> list[ExamAttemptRecord]:
        ids = set(practical_ids)
        return [a for a in self.exam_attempts.values() if a.practical_id in ids]
