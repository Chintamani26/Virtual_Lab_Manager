"""Cloud Firestore repository — the production store for Firebase deployments.

Data model, indexes and security rules: docs/FIRESTORE_DESIGN.md, firebase/firestore.rules,
firebase/firestore.indexes.json.

* Collections are top-level and snake_case; documents are ``Record.model_dump()`` (python mode, so
  datetimes are stored as Firestore timestamps) and read back with ``Record.model_validate``.
* Join/one-per-pair documents use ``{a}__{b}`` ids (enrollments, drafts, exam attempts).
* Only this backend writes (Admin credentials bypass rules). Browsers read just ``users/{own}`` and the
  ``exam_live`` mirror, which never contains the exam's active session id (the one-tab claim secret).
* Nothing is written on startup.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta
from typing import Any, Protocol, TypeVar

from google.cloud.firestore_v1.base_query import FieldFilter

from app.db.base import Repository, append_to_thread, merge_tally, tally_event
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
    utcnow,
)

DEPARTMENTS = "departments"
USERS = "users"
COURSES = "courses"
ENROLLMENTS = "course_enrollments"
PRACTICALS = "practicals"
DRAFTS = "practical_drafts"
SUBMISSIONS = "submissions"
EXECUTIONS = "execution_logs"
HINTS = "ai_hint_logs"
SESSIONS = "proctoring_sessions"
EVENTS = "proctoring_events"
ATTEMPTS = "exam_attempts"
LIVE = "exam_live"
TUTOR_THREADS = "tutor_threads"  # {practical_id}__{student_id}: one AI Lab Tutor conversation (never seeded)
ALL_COLLECTIONS = (DEPARTMENTS, USERS, COURSES, ENROLLMENTS, PRACTICALS, DRAFTS, SUBMISSIONS, EXECUTIONS, HINTS,
                   SESSIONS, EVENTS, ATTEMPTS, LIVE, TUTOR_THREADS)

IN_LIMIT = 30            # Firestore: max values in an `in` filter
BATCH_LIMIT = 500        # Firestore: max writes per batch
GET_ALL_CHUNK = 100
TELEMETRY_TTL = timedelta(days=180)   # TTL policy on `expire_at` (docs/FIRESTORE_DESIGN.md §6)
MAX_OUTPUT_CHARS = 64_000             # keep execution logs far below the 1 MiB document limit
# Firestore bills every document read. Users, courses, practicals and enrolments are read on nearly every
# request but change rarely, so this process keeps them for a short time. Writes made through this process
# replace / drop the cached copy at once; changes made elsewhere (seed scripts, another instance) show up
# within CACHE_TTL_S.
CACHE_TTL_S = 60.0
RUNS_OVERLAP = timedelta(seconds=30)  # live monitor re-reads this much before its watermark (late commits)
# A proctoring session that hasn't been seen for this long gets no new events (each batch updates
# last_seen_at before writing its events), so its event totals can be kept instead of re-read every poll.
IDLE_SESSION = timedelta(minutes=2)


class _TtlCache:
    """Small per-process cache. Values are pydantic models / lists of ids; callers get deep copies."""

    def __init__(self, ttl_s: float) -> None:
        self.ttl_s = ttl_s
        self._data: dict[tuple[str, str], tuple[float, Any]] = {}

    def get(self, kind: str, key: str) -> Any | None:
        hit = self._data.get((kind, key))
        if hit is None:
            return None
        if time.monotonic() - hit[0] > self.ttl_s:
            self._data.pop((kind, key), None)
            return None
        value = hit[1]
        return value.model_copy(deep=True) if hasattr(value, "model_copy") else list(value)

    def put(self, kind: str, key: str, value: Any) -> None:
        if self.ttl_s > 0:
            self._data[(kind, key)] = (time.monotonic(), value.model_copy(deep=True) if hasattr(value, "model_copy") else value)

    def drop(self, kind: str, key: str) -> None:
        self._data.pop((kind, key), None)
HEARTBEAT_PERSIST_EVERY = timedelta(seconds=15)  # exam.LIVE_WINDOW is 20 s, ONLINE_WINDOW 30 s
LIVE_FIELDS = ("status", "lock_reason", "violations", "locked_at", "unlocked_at", "submitted_at", "paused_at",
               "breaks_used")

_EXEC_LIGHT_FIELDS = ["id", "practical_id", "student_id", "lab_type", "mode", "engine", "status", "test_results",
                      "tests_passed", "tests_total", "duration_ms", "created_at"]
_SESSION_LIGHT_FIELDS = ["id", "practical_id", "student_id", "stats", "started_at", "last_seen_at"]

M = TypeVar("M")
T = TypeVar("T")


def pair_id(a: str, b: str) -> str:
    return f"{a}__{b}"


def _chunks(values: Iterable[str], size: int = IN_LIMIT) -> list[list[str]]:
    vals = sorted(set(values))
    return [vals[i:i + size] for i in range(0, len(vals), size)]


def _cap(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n… [truncated {len(text) - MAX_OUTPUT_CHARS} characters]"


# ---------------------------------------------------------------- record -> document
def _dump(rec: Any) -> dict:
    return rec.model_dump(mode="python")


def user_doc(u: UserRecord, *, include_password_hash: bool = True) -> dict:
    d = _dump(u)
    d["email_lower"] = u.email.strip().lower()
    if not include_password_hash:
        d["password_hash"] = ""  # Firebase Authentication holds the credential
    return d


def department_doc(dep: Department, hod_ids: list[str]) -> dict:
    return {**_dump(dep), "hod_ids": sorted(hod_ids)}


def practical_doc(p: PracticalRecord, department_id: str | None) -> dict:
    return {**_dump(p), "department_id": department_id}


def execution_doc(e: ExecutionLogRecord) -> dict:
    d = _dump(e)
    d["stdout"], d["stderr"] = _cap(e.stdout), _cap(e.stderr)
    d["expire_at"] = e.created_at + TELEMETRY_TTL
    return d


def session_doc(s: ProctorSessionRecord) -> dict:
    return {**_dump(s), "expire_at": s.started_at + TELEMETRY_TTL}


def event_doc(e: ProctorEventRecord) -> dict:
    return {**_dump(e), "expire_at": e.created_at + TELEMETRY_TTL}


def enrollment_doc(course_id: str, student_id: str, department_id: str | None, enrolled_at: datetime) -> dict:
    return {"course_id": course_id, "student_id": student_id, "department_id": department_id, "enrolled_at": enrolled_at}


def seed_documents(seed: SeedBundle, *, include_password_hash: bool) -> list[tuple[str, str, dict]]:
    """Every seed record as (collection, document id, data) — shared by the seed script and the tests."""
    course_dept = {c.id: c.department_id for c in seed.courses}
    hods: dict[str, list[str]] = {}
    for u in seed.users:
        if u.role == "hod":
            hods.setdefault(u.department_id, []).append(u.id)
    docs: list[tuple[str, str, dict]] = []
    docs += [(DEPARTMENTS, d.id, department_doc(d, hods.get(d.id, []))) for d in seed.departments]
    docs += [(USERS, u.id, user_doc(u, include_password_hash=include_password_hash)) for u in seed.users]
    docs += [(COURSES, c.id, _dump(c)) for c in seed.courses]
    created = {c.id: c.created_at for c in seed.courses}
    docs += [(ENROLLMENTS, pair_id(cid, sid), enrollment_doc(cid, sid, course_dept.get(cid), created.get(cid, utcnow())))
             for cid, sid in seed.enrollments]
    docs += [(PRACTICALS, p.id, practical_doc(p, course_dept.get(p.course_id))) for p in seed.practicals]
    docs += [(DRAFTS, pair_id(d.practical_id, d.student_id), _dump(d)) for d in seed.drafts]
    docs += [(SUBMISSIONS, s.id, _dump(s)) for s in seed.submissions]
    docs += [(EXECUTIONS, e.id, execution_doc(e)) for e in seed.execution_logs]
    docs += [(HINTS, h.id, _dump(h)) for h in seed.hint_logs]
    docs += [(SESSIONS, s.id, session_doc(s)) for s in seed.proctor_sessions]
    docs += [(EVENTS, e.id, event_doc(e)) for e in seed.proctor_events]
    return docs


async def write_documents(client: Any, docs: list[tuple[str, str, dict]]) -> int:
    """Batched `set` (≤ 500 per batch). Idempotent: same ids overwrite, nothing is deleted."""
    written = 0
    for i in range(0, len(docs), BATCH_LIMIT):
        batch = client.batch()
        for collection, doc_id, data in docs[i:i + BATCH_LIMIT]:
            batch.set(client.collection(collection).document(doc_id), data)
        await batch.commit()
        written += len(docs[i:i + BATCH_LIMIT])
    return written


# ---------------------------------------------------------------- transaction seam
class Txn(Protocol):
    async def get(self, ref: Any) -> Any: ...
    def set(self, ref: Any, data: dict) -> None: ...


TxnRunner = Callable[[Callable[[Txn], Awaitable[T]]], Awaitable[T]]


class _FirestoreTxn:
    def __init__(self, transaction: Any) -> None:
        self._t = transaction

    async def get(self, ref: Any) -> Any:
        return await ref.get(transaction=self._t)

    def set(self, ref: Any, data: dict) -> None:
        self._t.set(ref, data)


def firestore_transaction_runner(client: Any) -> TxnRunner:
    from google.cloud.firestore import async_transactional

    async def run(fn: Callable[[Txn], Awaitable[T]]) -> T:
        @async_transactional
        async def body(transaction):
            return await fn(_FirestoreTxn(transaction))

        return await body(client.transaction())

    return run


# ---------------------------------------------------------------- repository
class FirestoreRepository(Repository):
    name = "firestore"

    def __init__(self, client: Any, *, transact: TxnRunner | None = None, cache_ttl_s: float = CACHE_TTL_S) -> None:
        self.client = client
        self._transact = transact or firestore_transaction_runner(client)
        self._cache = _TtlCache(cache_ttl_s)                    # users, courses, practicals, enrolments
        self._runs: dict[str, tuple[datetime, dict[str, ExecutionLogRecord]]] = {}  # live monitor watermark
        self._tallies: dict[str, tuple[datetime, dict[str, int]]] = {}  # idle session id -> (last_seen_at, totals)
        self._subs: dict[str, tuple[float, dict[str, SubmissionRecord]]] = {}  # practical id -> latest per student
        self._scope: dict[str, tuple[str, str | None]] = {}   # practical_id -> (course_id, department_id)
        self._hods: dict[str, list[str]] = {}                   # department_id -> HOD user ids
        self._names: dict[str, str] = {}                        # student_id -> full name
        self._persisted: dict[str, dict] = {}                   # exam attempt id -> last written document
        self._mirrored: dict[str, dict] = {}                    # exam attempt id -> last exam_live fields

    @classmethod
    def from_settings(cls, settings: Any) -> "FirestoreRepository":
        from google.cloud import firestore

        if not settings.gcp_project:
            raise RuntimeError("STORAGE=firestore needs GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID")
        return cls(firestore.AsyncClient(project=settings.gcp_project, database=settings.firestore_database))

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            res = close()
            if hasattr(res, "__await__"):
                await res

    # ---- low-level helpers
    def _ref(self, collection: str, doc_id: str) -> Any:
        return self.client.collection(collection).document(doc_id)

    async def _get(self, collection: str, doc_id: str, model: type[M]) -> M | None:
        snap = await self._ref(collection, doc_id).get()
        return model.model_validate(snap.to_dict()) if snap.exists else None  # type: ignore[attr-defined]

    async def _query(self, collection: str, filters: Iterable[tuple[str, str, Any]] = (), *,
                     order: tuple[str, str] | None = None, limit: int | None = None,
                     select: list[str] | None = None) -> list[dict]:
        q: Any = self.client.collection(collection)
        for field, op, value in filters:
            q = q.where(filter=FieldFilter(field, op, value))
        if select is not None:
            q = q.select(select)
        if order is not None:
            q = q.order_by(order[0], direction=order[1])
        if limit is not None:
            q = q.limit(limit)
        return [snap.to_dict() async for snap in q.stream()]

    async def _query_in(self, collection: str, field: str, values: Iterable[str],
                        extra: Iterable[tuple[str, str, Any]] = (), *, select: list[str] | None = None) -> list[dict]:
        out: list[dict] = []
        for chunk in _chunks(values):
            out += await self._query(collection, [(field, "in", chunk), *extra], select=select)
        return out

    async def _get_many(self, collection: str, ids: Iterable[str]) -> list[dict]:
        out: list[dict] = []
        for chunk in _chunks(ids, GET_ALL_CHUNK):
            refs = [self._ref(collection, i) for i in chunk]
            async for snap in self.client.get_all(refs):
                if snap.exists:
                    out.append(snap.to_dict())
        return out

    async def _set_many(self, items: list[tuple[str, str, dict]]) -> None:
        await write_documents(self.client, items)

    # ---- departments / users
    async def get_department(self, department_id: str) -> Department | None:
        return await self._get(DEPARTMENTS, department_id, Department)

    async def get_user(self, user_id: str) -> UserRecord | None:
        cached = self._cache.get(USERS, user_id)
        if cached is not None:
            return cached
        user = await self._get(USERS, user_id, UserRecord)
        if user is not None:
            self._cache.put(USERS, user_id, user)
        return user

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        rows = await self._query(USERS, [("email_lower", "==", email.strip().lower())], limit=1)
        return UserRecord.model_validate(rows[0]) if rows else None

    async def list_users(self, department_id: str, role: Role | None = None) -> list[UserRecord]:
        filters = [("department_id", "==", department_id)] + ([("role", "==", role)] if role else [])
        users = [UserRecord.model_validate(d) for d in await self._query(USERS, filters)]
        return sorted(users, key=lambda u: u.full_name)

    async def get_users(self, user_ids: list[str]) -> dict[str, UserRecord]:
        out: dict[str, UserRecord] = {}
        missing: list[str] = []
        for uid in dict.fromkeys(user_ids):
            cached = self._cache.get(USERS, uid)
            if cached is not None:
                out[uid] = cached
            else:
                missing.append(uid)
        for d in await self._get_many(USERS, missing) if missing else []:
            u = UserRecord.model_validate(d)
            self._cache.put(USERS, u.id, u)
            out[u.id] = u
        return out

    # ---- courses
    async def get_course(self, course_id: str) -> CourseRecord | None:
        cached = self._cache.get(COURSES, course_id)
        if cached is not None:
            return cached
        course = await self._get(COURSES, course_id, CourseRecord)
        if course is not None:
            self._cache.put(COURSES, course_id, course)
        return course

    async def list_courses(self, *, department_id=None, faculty_id=None, student_id=None) -> list[CourseRecord]:
        if student_id:
            ids = [d["course_id"] for d in await self._query(ENROLLMENTS, [("student_id", "==", student_id)])]
            docs = await self._get_many(COURSES, ids)
        elif faculty_id:
            docs = await self._query(COURSES, [("faculty_id", "==", faculty_id)])
        elif department_id:
            docs = await self._query(COURSES, [("department_id", "==", department_id)])
        else:
            docs = await self._query(COURSES)
        out = [CourseRecord.model_validate(d) for d in docs]
        out = [c for c in out if (not department_id or c.department_id == department_id)
               and (not faculty_id or c.faculty_id == faculty_id)]
        return sorted(out, key=lambda c: c.code)

    async def set_course_faculty(self, course_id: str, faculty_id: str) -> CourseRecord:
        await self._ref(COURSES, course_id).update({"faculty_id": faculty_id})
        self._cache.drop(COURSES, course_id)
        course = await self.get_course(course_id)
        assert course is not None
        # keep exam_live access (staff_ids) in step with the new assignment for exams still in progress
        live = await self._query(LIVE, [("course_id", "==", course_id), ("status", "in", ["active", "locked"])])
        if live:
            staff = await self._staff_ids(course, course.department_id)
            batch = self.client.batch()
            for d in live:
                batch.update(self._ref(LIVE, pair_id(d["practical_id"], d["student_id"])), {"staff_ids": staff})
            await batch.commit()
        return course

    async def list_enrollments(self, course_ids: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        missing: list[str] = []
        for cid in dict.fromkeys(course_ids):
            cached = self._cache.get(ENROLLMENTS, cid)
            if cached is not None:
                out[cid] = cached
            else:
                missing.append(cid)
        if missing:
            found: dict[str, list[str]] = {cid: [] for cid in missing}
            for d in await self._query_in(ENROLLMENTS, "course_id", missing):
                found.setdefault(d["course_id"], []).append(d["student_id"])
            for cid, sids in found.items():
                out[cid] = sorted(sids)
                self._cache.put(ENROLLMENTS, cid, list(out[cid]))
        return out

    async def is_enrolled(self, course_id: str, student_id: str) -> bool:
        """One document read (enrolment ids are `{course_id}__{student_id}`) instead of the whole course list."""
        cached = self._cache.get(ENROLLMENTS, course_id)
        if cached is not None:
            return student_id in cached
        key = pair_id(course_id, student_id)
        if self._cache.get("enrolled", key) is not None:
            return True
        snap = await self._ref(ENROLLMENTS, key).get()
        if snap.exists:
            self._cache.put("enrolled", key, [True])
        return bool(snap.exists)

    # ---- practicals
    async def get_practical(self, practical_id: str) -> PracticalRecord | None:
        cached = self._cache.get(PRACTICALS, practical_id)
        if cached is not None:
            return cached
        rec = await self._get(PRACTICALS, practical_id, PracticalRecord)
        if rec is not None:
            self._cache.put(PRACTICALS, practical_id, rec)
        return rec

    async def list_practicals(self, course_ids: list[str], published_only: bool = False) -> list[PracticalRecord]:
        extra = [("status", "==", "published")] if published_only else []
        out = [PracticalRecord.model_validate(d) for d in await self._query_in(PRACTICALS, "course_id", course_ids, extra)]
        return sorted(out, key=lambda p: (p.due_at is None, p.due_at or p.created_at, p.title))

    async def _write_practical(self, rec: PracticalRecord) -> PracticalRecord:
        course = await self.get_course(rec.course_id)
        await self._ref(PRACTICALS, rec.id).set(practical_doc(rec, course.department_id if course else None))
        self._scope.pop(rec.id, None)
        self._cache.put(PRACTICALS, rec.id, rec)
        return rec

    async def create_practical(self, rec: PracticalRecord) -> PracticalRecord:
        return await self._write_practical(rec)

    async def update_practical(self, rec: PracticalRecord) -> PracticalRecord:
        return await self._write_practical(rec)

    # ---- drafts
    async def get_draft(self, practical_id: str, student_id: str) -> DraftRecord | None:
        return await self._get(DRAFTS, pair_id(practical_id, student_id), DraftRecord)

    async def upsert_draft(self, rec: DraftRecord) -> DraftRecord:
        await self._ref(DRAFTS, pair_id(rec.practical_id, rec.student_id)).set(_dump(rec))
        return rec

    # ---- submissions
    async def create_submission(self, rec: SubmissionRecord) -> SubmissionRecord:
        await self._ref(SUBMISSIONS, rec.id).set(_dump(rec))
        self._subs.pop(rec.practical_id, None)
        return rec

    async def update_submission(self, rec: SubmissionRecord) -> SubmissionRecord:
        await self._ref(SUBMISSIONS, rec.id).set(_dump(rec))
        self._subs.pop(rec.practical_id, None)
        return rec

    async def latest_submissions(self, practical_id: str) -> dict[str, SubmissionRecord]:
        # polled by the Live Lab Monitor; submissions made / reviewed through this process drop the copy at once
        hit = self._subs.get(practical_id)
        if hit is not None and time.monotonic() - hit[0] <= self._cache.ttl_s:
            return dict(hit[1])
        latest = await super().latest_submissions(practical_id)
        if self._cache.ttl_s > 0:
            self._subs[practical_id] = (time.monotonic(), latest)
        return dict(latest)

    async def get_submission(self, submission_id: str) -> SubmissionRecord | None:
        return await self._get(SUBMISSIONS, submission_id, SubmissionRecord)

    async def list_submissions(self, *, practical_ids=None, student_id=None) -> list[SubmissionRecord]:
        if practical_ids is not None:
            extra = [("student_id", "==", student_id)] if student_id else []
            docs = await self._query_in(SUBMISSIONS, "practical_id", practical_ids, extra)
        elif student_id:
            docs = await self._query(SUBMISSIONS, [("student_id", "==", student_id)])
        else:
            docs = await self._query(SUBMISSIONS)
        out = [SubmissionRecord.model_validate(d) for d in docs]
        return sorted(out, key=lambda s: s.submitted_at, reverse=True)

    # ---- execution logs
    async def create_execution_log(self, rec: ExecutionLogRecord) -> ExecutionLogRecord:
        await self._ref(EXECUTIONS, rec.id).set(execution_doc(rec))
        return rec

    async def get_latest_execution(self, practical_id: str, student_id: str, mode: str = "test"):
        rows = await self._query(
            EXECUTIONS,
            [("practical_id", "==", practical_id), ("student_id", "==", student_id), ("mode", "==", mode)],
            order=("created_at", "DESCENDING"), limit=1,
        )
        return ExecutionLogRecord.model_validate(rows[0]) if rows else None

    async def list_execution_logs(self, practical_ids: list[str], since: datetime | None = None):
        extra = [("created_at", ">=", since)] if since is not None else []
        docs = await self._query_in(EXECUTIONS, "practical_id", practical_ids, extra, select=_EXEC_LIGHT_FIELDS)
        return [ExecutionLogRecord.model_validate({**d, "files": {}, "stdout": "", "stderr": ""}) for d in docs]

    async def list_student_execution_logs(self, student_id: str, practical_ids: list[str]) -> list[ExecutionLogRecord]:
        # only this student's documents (single-field index), not every classmate's runs
        if not practical_ids:
            return []
        wanted = set(practical_ids)
        docs = await self._query(EXECUTIONS, [("student_id", "==", student_id)], select=_EXEC_LIGHT_FIELDS)
        return [ExecutionLogRecord.model_validate({**d, "files": {}, "stdout": "", "stderr": ""})
                for d in docs if d.get("practical_id") in wanted]

    async def latest_test_runs(self, practical_id: str) -> dict[str, ExecutionLogRecord]:
        # Logs are append-only: after the first poll, read only those created since the last one
        # (index practical_id + created_at), overlapping a little for writes that commit late.
        prev = self._runs.get(practical_id)
        since = prev[0] - RUNS_OVERLAP if prev else None
        latest = dict(prev[1]) if prev else {}
        watermark = prev[0] if prev else None
        for e in await self.list_execution_logs([practical_id], since=since):
            watermark = e.created_at if watermark is None or e.created_at > watermark else watermark
            cur = latest.get(e.student_id)
            if e.mode == "test" and (cur is None or e.created_at >= cur.created_at):
                latest[e.student_id] = e
        if watermark is not None:
            self._runs[practical_id] = (watermark, latest)
        return dict(latest)

    # ---- hints
    async def create_hint_log(self, rec: HintLogRecord) -> HintLogRecord:
        await self._ref(HINTS, rec.id).set(_dump(rec))
        return rec

    async def list_hint_logs(self, *, practical_ids=None, student_id=None) -> list[HintLogRecord]:
        if practical_ids is not None:
            extra = [("student_id", "==", student_id)] if student_id else []
            docs = await self._query_in(HINTS, "practical_id", practical_ids, extra)
        elif student_id:
            docs = await self._query(HINTS, [("student_id", "==", student_id)])
        else:
            docs = await self._query(HINTS)
        return sorted((HintLogRecord.model_validate(d) for d in docs), key=lambda h: h.created_at)

    # ---- AI Lab Tutor conversations (one document per student per practical: one read per chat turn)
    async def get_tutor_thread(self, practical_id: str, student_id: str) -> TutorThreadRecord | None:
        return await self._get(TUTOR_THREADS, pair_id(practical_id, student_id), TutorThreadRecord)

    async def append_tutor_messages(self, practical_id: str, student_id: str,
                                    messages: list[TutorMessage]) -> TutorThreadRecord:
        ref = self._ref(TUTOR_THREADS, pair_id(practical_id, student_id))

        async def fn(t: Txn) -> TutorThreadRecord:
            snap = await t.get(ref)
            cur = TutorThreadRecord.model_validate(snap.to_dict()) if snap.exists else None
            new = append_to_thread(cur, practical_id, student_id, messages)
            t.set(ref, _dump(new))
            return new

        return await self._transact(fn)

    async def list_tutor_threads(self, practical_ids: list[str]) -> list[TutorThreadRecord]:
        # single-field index on practical_id (automatic); one read per thread
        if not practical_ids:
            return []
        return [TutorThreadRecord.model_validate(d)
                for d in await self._query_in(TUTOR_THREADS, "practical_id", practical_ids)]

    # ---- proctoring
    async def create_proctor_events(self, events: list[ProctorEventRecord]) -> None:
        await self._set_many([(EVENTS, e.id, event_doc(e)) for e in events])

    async def list_proctor_events(self, practical_id: str, student_id: str) -> list[ProctorEventRecord]:
        docs = await self._query(EVENTS, [("practical_id", "==", practical_id), ("student_id", "==", student_id)])
        return sorted((ProctorEventRecord.model_validate(d) for d in docs), key=lambda e: (e.occurred_at, e.created_at))

    async def get_proctor_session(self, session_id: str) -> ProctorSessionRecord | None:
        return await self._get(SESSIONS, session_id, ProctorSessionRecord)

    async def upsert_proctor_session(self, rec: ProctorSessionRecord) -> ProctorSessionRecord | None:
        ref = self._ref(SESSIONS, rec.id)

        async def fn(t: Txn) -> ProctorSessionRecord | None:
            snap = await t.get(ref)
            if not snap.exists:
                t.set(ref, session_doc(rec))
                return rec
            cur = ProctorSessionRecord.model_validate(snap.to_dict())
            if cur.student_id != rec.student_id or cur.practical_id != rec.practical_id:
                return None  # session id belongs to someone else — never hijack it
            cur = cur.model_copy(update={"stats": rec.stats, "last_seen_at": rec.last_seen_at})
            t.set(ref, session_doc(cur))
            return cur

        return await self._transact(fn)

    async def list_proctor_sessions(self, practical_id: str, student_id: str) -> list[ProctorSessionRecord]:
        docs = await self._query(SESSIONS, [("practical_id", "==", practical_id), ("student_id", "==", student_id)])
        return sorted((ProctorSessionRecord.model_validate(d) for d in docs), key=lambda s: s.started_at)

    async def list_practical_proctor_sessions(self, practical_id: str) -> list[ProctorSessionRecord]:
        docs = await self._query(SESSIONS, [("practical_id", "==", practical_id)], select=_SESSION_LIGHT_FIELDS)
        return sorted((ProctorSessionRecord.model_validate({**d, "baseline_files": {}}) for d in docs),
                      key=lambda s: s.started_at)

    async def list_practical_proctor_events(self, practical_id: str) -> list[ProctorEventRecord]:
        docs = await self._query(EVENTS, [("practical_id", "==", practical_id)])
        return sorted((ProctorEventRecord.model_validate(d) for d in docs), key=lambda e: e.occurred_at)

    async def practical_proctor_tallies(
        self, practical_id: str, sessions: list[ProctorSessionRecord]
    ) -> dict[str, dict[str, int]]:
        # Read events only for sessions that are active or not tallied yet; idle sessions keep their totals.
        now = utcnow()
        out: dict[str, dict[str, int]] = {}
        fetch: list[ProctorSessionRecord] = []
        for s in sessions:
            hit = self._tallies.get(s.id)
            if hit is not None and hit[0] == s.last_seen_at:
                merge_tally(out.setdefault(s.student_id, {}), hit[1])
            else:
                fetch.append(s)
        if fetch:
            per_session: dict[str, dict[str, int]] = {s.id: {} for s in fetch}
            for d in await self._query_in(EVENTS, "session_id", [s.id for s in fetch]):
                e = ProctorEventRecord.model_validate(d)
                if e.session_id in per_session:
                    tally_event(per_session[e.session_id], e)
            for s in fetch:
                totals = per_session[s.id]
                if now - s.last_seen_at > IDLE_SESSION:
                    self._tallies[s.id] = (s.last_seen_at, dict(totals))
                merge_tally(out.setdefault(s.student_id, {}), totals)
        return out

    # ---- exam lockdown
    async def get_exam_attempt(self, practical_id: str, student_id: str) -> ExamAttemptRecord | None:
        return await self._get(ATTEMPTS, pair_id(practical_id, student_id), ExamAttemptRecord)

    async def save_exam_attempt(self, rec: ExamAttemptRecord) -> ExamAttemptRecord:
        key = pair_id(rec.practical_id, rec.student_id)
        doc = _dump(rec)
        prev = self._persisted.get(key)
        if prev is not None and self._heartbeat_only(prev, doc):
            return rec  # throttle: persist heartbeats at most every HEARTBEAT_PERSIST_EVERY
        live_fields = {f: doc[f] for f in LIVE_FIELDS}
        batch = self.client.batch()
        batch.set(self._ref(ATTEMPTS, key), doc)
        if self._mirrored.get(key) != live_fields:
            batch.set(self._ref(LIVE, key), await self._live_doc(rec, live_fields))
        await batch.commit()
        self._persisted[key] = doc
        self._mirrored[key] = live_fields
        return rec

    @staticmethod
    def _heartbeat_only(prev: dict, doc: dict) -> bool:
        if {k: v for k, v in prev.items() if k != "last_heartbeat_at"} != \
                {k: v for k, v in doc.items() if k != "last_heartbeat_at"}:
            return False
        old, new = prev.get("last_heartbeat_at"), doc.get("last_heartbeat_at")
        return old is not None and new is not None and timedelta(0) <= new - old < HEARTBEAT_PERSIST_EVERY

    async def list_exam_attempts(self, practical_ids: list[str]) -> list[ExamAttemptRecord]:
        return [ExamAttemptRecord.model_validate(d) for d in await self._query_in(ATTEMPTS, "practical_id", practical_ids)]

    # ---- exam_live mirror (browser-readable; see firebase/firestore.rules)
    async def _live_doc(self, a: ExamAttemptRecord, live_fields: dict) -> dict:
        course_id, department_id = await self._practical_scope(a.practical_id)
        course = await self.get_course(course_id) if course_id else None
        return {
            "practical_id": a.practical_id,
            "student_id": a.student_id,
            "student_name": await self._student_name(a.student_id),
            "course_id": course_id,
            "department_id": department_id,
            "staff_ids": await self._staff_ids(course, department_id),
            **live_fields,
            "updated_at": utcnow(),
        }

    async def _practical_scope(self, practical_id: str) -> tuple[str, str | None]:
        if practical_id not in self._scope:
            p = await self.get_practical(practical_id)
            course = await self.get_course(p.course_id) if p else None
            self._scope[practical_id] = (p.course_id if p else "", course.department_id if course else None)
        return self._scope[practical_id]

    async def _staff_ids(self, course: CourseRecord | None, department_id: str | None) -> list[str]:
        staff = [course.faculty_id] if course and course.faculty_id else []
        if department_id:
            if department_id not in self._hods:
                dep = (await self._ref(DEPARTMENTS, department_id).get())
                hods = (dep.to_dict() or {}).get("hod_ids") if dep.exists else None
                if hods is None:
                    hods = [u.id for u in await self.list_users(department_id, "hod")]
                self._hods[department_id] = list(hods)
            staff += self._hods[department_id]
        return sorted(set(staff))

    async def _student_name(self, student_id: str) -> str:
        if student_id not in self._names:
            u = await self.get_user(student_id)
            self._names[student_id] = u.full_name if u else ""
        return self._names[student_id]
