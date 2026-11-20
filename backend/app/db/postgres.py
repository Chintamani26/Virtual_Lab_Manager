"""PostgreSQL repository (AlloyDB / Cloud SQL / Supabase) using asyncpg.

Schema: database/001_schema.sql. The app only needs SELECT/INSERT/UPDATE privileges
(see database/003_app_role.sql); it never runs DDL.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, TypeVar

import asyncpg
from pydantic import BaseModel

from app.db.base import TUTOR_THREAD_LIMIT, Repository
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

M = TypeVar("M", bound=BaseModel)


def _clean(row: asyncpg.Record) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(row).items()}


def _one(model: type[M], row: asyncpg.Record | None) -> M | None:
    return model.model_validate(_clean(row)) if row is not None else None


def _many(model: type[M], rows: list[asyncpg.Record]) -> list[M]:
    return [model.model_validate(_clean(r)) for r in rows]


def _dump(items: list[BaseModel]) -> list[dict]:
    return [i.model_dump() for i in items]


class PostgresRepository(Repository):
    name = "postgres"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        async def init(conn: asyncpg.Connection) -> None:
            for typ in ("json", "jsonb"):
                await conn.set_type_codec(typ, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10, init=init, command_timeout=15)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    @property
    def db(self) -> asyncpg.Pool:
        assert self.pool is not None, "PostgresRepository.connect() was not called"
        return self.pool

    # ---- departments / users
    async def get_department(self, department_id: str) -> Department | None:
        return _one(Department, await self.db.fetchrow("SELECT * FROM departments WHERE id = $1", department_id))

    async def get_user(self, user_id: str) -> UserRecord | None:
        return _one(UserRecord, await self.db.fetchrow("SELECT * FROM users WHERE id = $1", user_id))

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        row = await self.db.fetchrow("SELECT * FROM users WHERE lower(email) = lower($1)", email.strip())
        return _one(UserRecord, row)

    async def list_users(self, department_id: str, role: Role | None = None) -> list[UserRecord]:
        rows = await self.db.fetch(
            "SELECT * FROM users WHERE department_id = $1 AND ($2::text IS NULL OR role = $2) ORDER BY full_name",
            department_id,
            role,
        )
        return _many(UserRecord, rows)

    async def get_users(self, user_ids: list[str]) -> dict[str, UserRecord]:
        if not user_ids:
            return {}
        rows = await self.db.fetch("SELECT * FROM users WHERE id = ANY($1::uuid[])", list(set(user_ids)))
        return {u.id: u for u in _many(UserRecord, rows)}

    # ---- courses
    async def get_course(self, course_id: str) -> CourseRecord | None:
        return _one(CourseRecord, await self.db.fetchrow("SELECT * FROM courses WHERE id = $1", course_id))

    async def list_courses(self, *, department_id=None, faculty_id=None, student_id=None) -> list[CourseRecord]:
        rows = await self.db.fetch(
            """
            SELECT c.* FROM courses c
            WHERE ($1::uuid IS NULL OR c.department_id = $1)
              AND ($2::uuid IS NULL OR c.faculty_id = $2)
              AND ($3::uuid IS NULL OR EXISTS (
                    SELECT 1 FROM course_enrollments e WHERE e.course_id = c.id AND e.student_id = $3))
            ORDER BY c.code
            """,
            department_id,
            faculty_id,
            student_id,
        )
        return _many(CourseRecord, rows)

    async def set_course_faculty(self, course_id: str, faculty_id: str) -> CourseRecord:
        row = await self.db.fetchrow(
            "UPDATE courses SET faculty_id = $2 WHERE id = $1 RETURNING *", course_id, faculty_id
        )
        if row is None:
            raise KeyError(course_id)
        return _one(CourseRecord, row)  # type: ignore[return-value]

    async def list_enrollments(self, course_ids: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {cid: [] for cid in course_ids}
        if not course_ids:
            return out
        rows = await self.db.fetch(
            "SELECT course_id, student_id FROM course_enrollments WHERE course_id = ANY($1::uuid[]) ORDER BY student_id",
            course_ids,
        )
        for r in rows:
            out.setdefault(str(r["course_id"]), []).append(str(r["student_id"]))
        return out

    # ---- practicals
    async def get_practical(self, practical_id: str) -> PracticalRecord | None:
        return _one(PracticalRecord, await self.db.fetchrow("SELECT * FROM practicals WHERE id = $1", practical_id))

    async def list_practicals(self, course_ids: list[str], published_only: bool = False) -> list[PracticalRecord]:
        if not course_ids:
            return []
        rows = await self.db.fetch(
            """
            SELECT * FROM practicals
            WHERE course_id = ANY($1::uuid[]) AND (NOT $2::boolean OR status = 'published')
            ORDER BY due_at NULLS LAST, created_at, title
            """,
            course_ids,
            published_only,
        )
        return _many(PracticalRecord, rows)

    async def create_practical(self, rec: PracticalRecord) -> PracticalRecord:
        row = await self.db.fetchrow(
            """
            INSERT INTO practicals (id, course_id, title, description, lab_type, language, starter_files,
                                    test_cases, rubric, max_score, due_at, status, created_by, created_at, updated_at,
                                    proctored, lockdown_mode, seb_config_key, seb_config_url, worksheet)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
            RETURNING *
            """,
            rec.id, rec.course_id, rec.title, rec.description, rec.lab_type, rec.language, rec.starter_files,
            _dump(rec.test_cases), _dump(rec.rubric), rec.max_score, rec.due_at, rec.status, rec.created_by,
            rec.created_at, rec.updated_at, rec.proctored, rec.lockdown_mode, rec.seb_config_key, rec.seb_config_url,
            rec.worksheet.model_dump() if rec.worksheet else None,
        )
        return _one(PracticalRecord, row)  # type: ignore[return-value]

    async def update_practical(self, rec: PracticalRecord) -> PracticalRecord:
        row = await self.db.fetchrow(
            """
            UPDATE practicals SET course_id = $2, title = $3, description = $4, lab_type = $5, language = $6,
                   starter_files = $7, test_cases = $8, rubric = $9, max_score = $10, due_at = $11,
                   status = $12, updated_at = $13, proctored = $14, lockdown_mode = $15, seb_config_key = $16,
                   seb_config_url = $17, worksheet = $18
            WHERE id = $1
            RETURNING *
            """,
            rec.id, rec.course_id, rec.title, rec.description, rec.lab_type, rec.language, rec.starter_files,
            _dump(rec.test_cases), _dump(rec.rubric), rec.max_score, rec.due_at, rec.status, rec.updated_at,
            rec.proctored, rec.lockdown_mode, rec.seb_config_key, rec.seb_config_url,
            rec.worksheet.model_dump() if rec.worksheet else None,
        )
        if row is None:
            raise KeyError(rec.id)
        return _one(PracticalRecord, row)  # type: ignore[return-value]

    # ---- drafts
    async def get_draft(self, practical_id: str, student_id: str) -> DraftRecord | None:
        row = await self.db.fetchrow(
            "SELECT * FROM practical_drafts WHERE practical_id = $1 AND student_id = $2", practical_id, student_id
        )
        return _one(DraftRecord, row)

    async def upsert_draft(self, rec: DraftRecord) -> DraftRecord:
        row = await self.db.fetchrow(
            """
            INSERT INTO practical_drafts (practical_id, student_id, files, updated_at) VALUES ($1, $2, $3, $4)
            ON CONFLICT (practical_id, student_id) DO UPDATE SET files = EXCLUDED.files, updated_at = EXCLUDED.updated_at
            RETURNING *
            """,
            rec.practical_id, rec.student_id, rec.files, rec.updated_at,
        )
        return _one(DraftRecord, row)  # type: ignore[return-value]

    # ---- submissions
    _SUB_COLS = (
        "id, practical_id, student_id, files, status, tests_passed, tests_total, test_results, rubric_score, "
        "max_score, rubric_breakdown, ai_feedback, grading_model, faculty_score, faculty_comment, submitted_at, "
        "graded_at, reviewed_at, integrity"
    )

    def _sub_args(self, s: SubmissionRecord) -> tuple:
        return (
            s.id, s.practical_id, s.student_id, s.files, s.status, s.tests_passed, s.tests_total,
            _dump(s.test_results), s.rubric_score, s.max_score, _dump(s.rubric_breakdown), s.ai_feedback,
            s.grading_model, s.faculty_score, s.faculty_comment, s.submitted_at, s.graded_at, s.reviewed_at,
            s.integrity.model_dump(mode="json") if s.integrity else None,
        )

    async def create_submission(self, rec: SubmissionRecord) -> SubmissionRecord:
        placeholders = ", ".join(f"${i}" for i in range(1, 20))
        row = await self.db.fetchrow(
            f"INSERT INTO submissions ({self._SUB_COLS}) VALUES ({placeholders}) RETURNING *", *self._sub_args(rec)
        )
        return _one(SubmissionRecord, row)  # type: ignore[return-value]

    async def update_submission(self, rec: SubmissionRecord) -> SubmissionRecord:
        row = await self.db.fetchrow(
            """
            UPDATE submissions SET status = $2, tests_passed = $3, tests_total = $4, test_results = $5,
                   rubric_score = $6, rubric_breakdown = $7, ai_feedback = $8, grading_model = $9,
                   faculty_score = $10, faculty_comment = $11, graded_at = $12, reviewed_at = $13, integrity = $14
            WHERE id = $1
            RETURNING *
            """,
            rec.id, rec.status, rec.tests_passed, rec.tests_total, _dump(rec.test_results), rec.rubric_score,
            _dump(rec.rubric_breakdown), rec.ai_feedback, rec.grading_model, rec.faculty_score,
            rec.faculty_comment, rec.graded_at, rec.reviewed_at,
            rec.integrity.model_dump(mode="json") if rec.integrity else None,
        )
        if row is None:
            raise KeyError(rec.id)
        return _one(SubmissionRecord, row)  # type: ignore[return-value]

    async def get_submission(self, submission_id: str) -> SubmissionRecord | None:
        return _one(SubmissionRecord, await self.db.fetchrow("SELECT * FROM submissions WHERE id = $1", submission_id))

    async def list_submissions(self, *, practical_ids=None, student_id=None) -> list[SubmissionRecord]:
        rows = await self.db.fetch(
            """
            SELECT * FROM submissions
            WHERE ($1::uuid[] IS NULL OR practical_id = ANY($1::uuid[]))
              AND ($2::uuid IS NULL OR student_id = $2)
            ORDER BY submitted_at DESC
            """,
            practical_ids,
            student_id,
        )
        return _many(SubmissionRecord, rows)

    # ---- execution logs
    async def create_execution_log(self, rec: ExecutionLogRecord) -> ExecutionLogRecord:
        await self.db.execute(
            """
            INSERT INTO execution_logs (id, practical_id, student_id, lab_type, mode, engine, status, files, stdout,
                                        stderr, test_results, tests_passed, tests_total, duration_ms, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            rec.id, rec.practical_id, rec.student_id, rec.lab_type, rec.mode, rec.engine, rec.status, rec.files,
            rec.stdout, rec.stderr, _dump(rec.test_results), rec.tests_passed, rec.tests_total, rec.duration_ms,
            rec.created_at,
        )
        return rec

    async def get_latest_execution(self, practical_id: str, student_id: str, mode: str = "test"):
        row = await self.db.fetchrow(
            """
            SELECT * FROM execution_logs WHERE practical_id = $1 AND student_id = $2 AND mode = $3
            ORDER BY created_at DESC LIMIT 1
            """,
            practical_id, student_id, mode,
        )
        return _one(ExecutionLogRecord, row)

    async def list_execution_logs(self, practical_ids: list[str], since: datetime | None = None):
        if not practical_ids:
            return []
        rows = await self.db.fetch(
            """
            SELECT id, practical_id, student_id, lab_type, mode, engine, status, '{}'::jsonb AS files,
                   '' AS stdout, '' AS stderr, test_results, tests_passed, tests_total, duration_ms, created_at
            FROM execution_logs
            WHERE practical_id = ANY($1::uuid[]) AND ($2::timestamptz IS NULL OR created_at >= $2)
            """,
            practical_ids,
            since,
        )
        return _many(ExecutionLogRecord, rows)

    # ---- hints
    async def create_hint_log(self, rec: HintLogRecord) -> HintLogRecord:
        await self.db.execute(
            """
            INSERT INTO ai_hint_logs (id, practical_id, student_id, execution_id, focus_test, hint_level, question,
                                      hint_text, model, source, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            rec.id, rec.practical_id, rec.student_id, rec.execution_id, rec.focus_test, rec.hint_level,
            rec.question, rec.hint_text, rec.model, rec.source, rec.created_at,
        )
        return rec

    async def list_hint_logs(self, *, practical_ids=None, student_id=None) -> list[HintLogRecord]:
        rows = await self.db.fetch(
            """
            SELECT * FROM ai_hint_logs
            WHERE ($1::uuid[] IS NULL OR practical_id = ANY($1::uuid[]))
              AND ($2::uuid IS NULL OR student_id = $2)
            ORDER BY created_at
            """,
            practical_ids,
            student_id,
        )
        return _many(HintLogRecord, rows)

    # ---- AI Lab Tutor conversations (database/008_tutor_conversations.sql). One row per message, so the full
    # history is kept for faculty audit; the thread returned to callers holds the newest TUTOR_THREAD_LIMIT.
    async def get_tutor_thread(self, practical_id: str, student_id: str) -> TutorThreadRecord | None:
        rows = await self.db.fetch(
            """
            SELECT message, created_at, count(*) OVER () AS total FROM ai_tutor_messages
            WHERE practical_id = $1 AND student_id = $2
            ORDER BY seq DESC
            LIMIT $3
            """,
            practical_id, student_id, TUTOR_THREAD_LIMIT,
        )
        if not rows:
            return None
        rows = list(reversed(rows))
        return TutorThreadRecord(
            practical_id=practical_id, student_id=student_id,
            messages=[TutorMessage.model_validate(r["message"]) for r in rows],
            dropped=max(0, int(rows[0]["total"]) - len(rows)),
            created_at=rows[0]["created_at"], updated_at=rows[-1]["created_at"],
        )

    async def append_tutor_messages(self, practical_id: str, student_id: str,
                                    messages: list[TutorMessage]) -> TutorThreadRecord:
        async with self.db.acquire() as conn, conn.transaction():
            await conn.executemany(
                """
                INSERT INTO ai_tutor_messages (id, practical_id, student_id, role, action, message, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [(m.id, practical_id, student_id, m.role, m.action, m.model_dump(mode="json"), m.created_at)
                 for m in messages],
            )
        thread = await self.get_tutor_thread(practical_id, student_id)
        assert thread is not None
        return thread

    async def list_tutor_threads(self, practical_ids: list[str]) -> list[TutorThreadRecord]:
        if not practical_ids:
            return []
        rows = await self.db.fetch(
            """
            SELECT practical_id, student_id, message, created_at FROM ai_tutor_messages
            WHERE practical_id = ANY($1::uuid[])
            ORDER BY seq
            """,
            practical_ids,
        )
        threads: dict[tuple[str, str], TutorThreadRecord] = {}
        for r in rows:
            key = (str(r["practical_id"]), str(r["student_id"]))
            t = threads.get(key)
            if t is None:
                t = threads[key] = TutorThreadRecord(practical_id=key[0], student_id=key[1], created_at=r["created_at"])
            t.messages.append(TutorMessage.model_validate(r["message"]))
            t.updated_at = r["created_at"]
        return list(threads.values())

    # ---- proctoring
    async def create_proctor_events(self, events: list[ProctorEventRecord]) -> None:
        if not events:
            return
        await self.db.executemany(
            """
            INSERT INTO proctoring_events (id, practical_id, student_id, session_id, event_type, detail, occurred_at,
                                           created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            [(e.id, e.practical_id, e.student_id, e.session_id, e.event_type, e.detail, e.occurred_at, e.created_at)
             for e in events],
        )

    async def list_proctor_events(self, practical_id: str, student_id: str) -> list[ProctorEventRecord]:
        rows = await self.db.fetch(
            """
            SELECT * FROM proctoring_events WHERE practical_id = $1 AND student_id = $2
            ORDER BY occurred_at, created_at LIMIT 5000
            """,
            practical_id, student_id,
        )
        return _many(ProctorEventRecord, rows)

    async def get_proctor_session(self, session_id: str) -> ProctorSessionRecord | None:
        row = await self.db.fetchrow("SELECT * FROM proctoring_sessions WHERE id = $1", session_id)
        return _one(ProctorSessionRecord, row)

    async def upsert_proctor_session(self, rec: ProctorSessionRecord) -> ProctorSessionRecord | None:
        row = await self.db.fetchrow(
            """
            INSERT INTO proctoring_sessions (id, practical_id, student_id, baseline_files, stats, started_at, last_seen_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET stats = EXCLUDED.stats, last_seen_at = EXCLUDED.last_seen_at
            WHERE proctoring_sessions.student_id = EXCLUDED.student_id
              AND proctoring_sessions.practical_id = EXCLUDED.practical_id
            RETURNING *
            """,
            rec.id, rec.practical_id, rec.student_id, rec.baseline_files, rec.stats, rec.started_at, rec.last_seen_at,
        )
        return _one(ProctorSessionRecord, row)

    async def list_proctor_sessions(self, practical_id: str, student_id: str) -> list[ProctorSessionRecord]:
        rows = await self.db.fetch(
            "SELECT * FROM proctoring_sessions WHERE practical_id = $1 AND student_id = $2 ORDER BY started_at",
            practical_id, student_id,
        )
        return _many(ProctorSessionRecord, rows)

    async def list_practical_proctor_sessions(self, practical_id: str) -> list[ProctorSessionRecord]:
        rows = await self.db.fetch(
            "SELECT id, practical_id, student_id, '{}'::jsonb AS baseline_files, stats, started_at, last_seen_at "
            "FROM proctoring_sessions WHERE practical_id = $1 ORDER BY started_at",
            practical_id,
        )
        return _many(ProctorSessionRecord, rows)

    async def list_practical_proctor_events(self, practical_id: str) -> list[ProctorEventRecord]:
        rows = await self.db.fetch(
            "SELECT * FROM proctoring_events WHERE practical_id = $1 ORDER BY occurred_at LIMIT 50000", practical_id
        )
        return _many(ProctorEventRecord, rows)

    # ---- exam lockdown
    async def get_exam_attempt(self, practical_id: str, student_id: str) -> ExamAttemptRecord | None:
        row = await self.db.fetchrow(
            "SELECT * FROM exam_attempts WHERE practical_id = $1 AND student_id = $2", practical_id, student_id
        )
        return _one(ExamAttemptRecord, row)

    async def save_exam_attempt(self, rec: ExamAttemptRecord) -> ExamAttemptRecord:
        row = await self.db.fetchrow(
            """
            INSERT INTO exam_attempts (id, practical_id, student_id, status, active_session_id, last_session_id,
                                       lock_reason, violations, unlock_count, started_at, last_heartbeat_at, locked_at,
                                       unlocked_at, unlocked_by, submitted_at, paused_at, breaks_used, break_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            ON CONFLICT (practical_id, student_id) DO UPDATE SET
                status = EXCLUDED.status, active_session_id = EXCLUDED.active_session_id,
                last_session_id = EXCLUDED.last_session_id, lock_reason = EXCLUDED.lock_reason,
                violations = EXCLUDED.violations, unlock_count = EXCLUDED.unlock_count,
                last_heartbeat_at = EXCLUDED.last_heartbeat_at, locked_at = EXCLUDED.locked_at,
                unlocked_at = EXCLUDED.unlocked_at, unlocked_by = EXCLUDED.unlocked_by,
                submitted_at = EXCLUDED.submitted_at, paused_at = EXCLUDED.paused_at,
                breaks_used = EXCLUDED.breaks_used, break_ms = EXCLUDED.break_ms
            RETURNING *
            """,
            rec.id, rec.practical_id, rec.student_id, rec.status, rec.active_session_id, rec.last_session_id,
            rec.lock_reason, rec.violations, rec.unlock_count, rec.started_at, rec.last_heartbeat_at, rec.locked_at,
            rec.unlocked_at, rec.unlocked_by, rec.submitted_at, rec.paused_at, rec.breaks_used, rec.break_ms,
        )
        return _one(ExamAttemptRecord, row)  # type: ignore[return-value]

    async def list_exam_attempts(self, practical_ids: list[str]) -> list[ExamAttemptRecord]:
        if not practical_ids:
            return []
        rows = await self.db.fetch("SELECT * FROM exam_attempts WHERE practical_id = ANY($1::uuid[])", practical_ids)
        return _many(ExamAttemptRecord, rows)
