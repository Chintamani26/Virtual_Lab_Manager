"""Request/response models for the HTTP API (see docs/API.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import re
import uuid

from pydantic import BaseModel, Field, field_validator

from app.models import (
    CLIENT_EVENT_TYPES,
    IntegrityReport,
    LabType,
    LockdownMode,
    PracticalStatus,
    Role,
    RubricCriterion,
    RubricScore,
    TestCaseSpec,
    TestResult,
    TutorAction,
    TutorMessage,
    WorksheetSpec,
)

MAX_FILES_BYTES = 300_000


_FILE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/ ]{0,119}$")
_RESERVED_NAME = re.compile(r"^__.*__$")  # Firestore reserves map keys like __name__


def _check_files(files: dict[str, str]) -> dict[str, str]:
    if len(files) > 5:
        raise ValueError("at most 5 files per lab")
    for name in files:
        # also keeps names storable as Firestore map keys (no empty / `__reserved__` names)
        # and rejects path traversal segments (`..`) or trailing slashes
        parts = name.split("/")
        if (
            not _FILE_NAME.match(name)
            or _RESERVED_NAME.match(name)
            or name.endswith("/")
            or any(p in ("", ".", "..") for p in parts)
        ):
            raise ValueError(f"invalid file name {name!r}")
    total = sum(len(k) + len(v.encode("utf-8")) for k, v in files.items())
    if total > MAX_FILES_BYTES:
        raise ValueError(f"files exceed {MAX_FILES_BYTES // 1000} KB")
    return files


# ---------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    department_id: str
    roll_number: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


class DemoAccount(BaseModel):
    role: Role
    email: str
    full_name: str
    password: str


# ---------------------------------------------------------------- courses / practicals
class CourseOut(BaseModel):
    id: str
    code: str
    title: str
    semester: int
    department_id: str
    faculty_id: str | None
    faculty_name: str | None
    enrolled: int


class PracticalOut(BaseModel):
    id: str
    course_id: str
    course_code: str
    course_title: str
    title: str
    description: str
    lab_type: LabType
    language: str
    starter_files: dict[str, str]
    test_cases: list[TestCaseSpec]
    hidden_test_count: int
    rubric: list[RubricCriterion]
    max_score: float
    due_at: datetime | None
    status: PracticalStatus
    proctored: bool
    lockdown_mode: LockdownMode
    seb_config_url: str | None = None
    seb_launch_url: str | None = None
    seb_config_key: str | None = None  # faculty/HOD only — never serialized to students
    worksheet: WorksheetSpec | None = None  # worksheet labs: what the student's worksheet renders
    created_at: datetime


class SubmissionOut(BaseModel):
    id: str
    practical_id: str
    practical_title: str
    course_code: str
    lab_type: LabType
    student_id: str
    student_name: str
    roll_number: str | None
    files: dict[str, str]
    status: Literal["graded", "reviewed"]
    tests_passed: int
    tests_total: int
    test_results: list[TestResult]
    rubric_score: float | None
    max_score: float
    rubric_breakdown: list[RubricScore]
    ai_feedback: str | None
    grading_model: str | None
    faculty_score: float | None
    faculty_comment: str | None
    final_score: float | None
    submitted_at: datetime
    graded_at: datetime | None
    reviewed_at: datetime | None
    integrity: IntegrityReport | None = None  # faculty/HOD only; always None in student endpoints


class ProctorSummary(BaseModel):
    sessions: int = 0
    paste_blocked: int = 0
    copy_blocked: int = 0
    focus_lost: int = 0
    time_away_ms: int = 0
    fullscreen_exits: int = 0
    devtools_blocked: int = 0
    large_insertions: int = 0
    breaks: int = 0  # declared breaks (Pause button)
    break_ms: int = 0


class ProctorEventIn(BaseModel):
    type: str
    at: datetime
    detail: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in CLIENT_EVENT_TYPES:
            raise ValueError(f"unknown proctoring event type '{v}'")
        return v

    @field_validator("detail")
    @classmethod
    def _small_detail(cls, v: dict) -> dict:
        if len(v) > 10:
            raise ValueError("detail has too many keys")
        return {k[:40]: (val[:200] if isinstance(val, str) else val) for k, val in v.items()}


class TypingStats(BaseModel):
    typed_chars: int = Field(default=0, ge=0, le=10_000_000)
    keystrokes: int = Field(default=0, ge=0, le=10_000_000)
    active_ms: int = Field(default=0, ge=0, le=7 * 24 * 3600 * 1000)
    large_insertions: int = Field(default=0, ge=0, le=100_000)
    large_insertion_chars: int = Field(default=0, ge=0, le=100_000_000)
    max_burst_cps: float = Field(default=0, ge=0, le=100_000)


class ProctorBatch(BaseModel):
    session_id: str
    events: list[ProctorEventIn] = Field(default_factory=list, max_length=100)
    stats: TypingStats | None = None

    @field_validator("session_id")
    @classmethod
    def _uuid(cls, v: str) -> str:
        return str(uuid.UUID(v))


class ProctorBatchResponse(BaseModel):
    accepted: int
    summary: ProctorSummary


class ProctorEventOut(BaseModel):
    id: str
    session_id: str
    type: str
    detail: dict
    occurred_at: datetime
    created_at: datetime


class ExamState(BaseModel):
    lockdown_mode: LockdownMode
    status: Literal["not_started", "active", "paused", "locked", "submitted"]
    lock_reason: str | None = None
    violations: int = 0
    locked_at: datetime | None = None
    is_current_session: bool = False   # this browser tab holds the exam
    awaiting_resume: bool = False      # a mentor unlocked; the tab must call /exam/start again
    seb_required: bool = False
    seb_verified: bool = False
    paused_at: datetime | None = None  # on a declared break since
    breaks_used: int = 0
    max_breaks: int = 0
    break_limit_s: int = 0


class ExamSessionBody(BaseModel):
    session_id: str

    @field_validator("session_id")
    @classmethod
    def _uuid(cls, v: str) -> str:
        return str(uuid.UUID(v))


class ExamViolationBody(ExamSessionBody):
    type: Literal["focus_lost", "fullscreen_exit", "devtools_blocked", "second_tab", "page_closed"]
    detail: str | None = Field(default=None, max_length=200)


class MentorLockBody(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class MonitorRow(BaseModel):
    student_id: str
    student_name: str
    roll_number: str | None
    status: Literal["not_started", "active", "paused", "locked", "submitted"]
    online: bool
    last_seen_at: datetime | None
    lock_reason: str | None
    locked_at: datetime | None
    violations: int
    unlock_count: int
    paste_blocked: int
    copy_blocked: int
    focus_lost: int
    fullscreen_exits: int
    time_away_ms: int
    tests_passed: int | None
    tests_total: int | None
    submission_id: str | None
    final_score: float | None
    max_score: float
    integrity_risk: Literal["low", "medium", "high"] | None
    paused_at: datetime | None = None
    breaks_used: int = 0
    break_ms: int = 0


class MonitorResponse(BaseModel):
    practical_id: str
    practical_title: str
    course_code: str
    lockdown_mode: LockdownMode
    proctored: bool
    generated_at: datetime
    counts: dict[str, int]
    rows: list[MonitorRow]


class LockAlert(BaseModel):
    practical_id: str
    practical_title: str
    course_code: str
    student_id: str
    student_name: str
    roll_number: str | None
    lock_reason: str | None
    locked_at: datetime | None


class AlertsResponse(BaseModel):
    locked_count: int
    locked: list[LockAlert]


class StudentPracticalOut(PracticalOut):
    draft_files: dict[str, str] | None
    draft_updated_at: datetime | None
    latest_submission: SubmissionOut | None
    hints_used: int
    proctoring_summary: ProctorSummary | None
    exam: ExamState | None  # null when lockdown_mode == "off"
    submission_limit: int  # submissions allowed per student (an exam ends at its first submission)
    submissions_used: int


class PracticalInput(BaseModel):
    course_id: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=20_000)
    lab_type: LabType
    starter_files: dict[str, str]
    test_cases: list[TestCaseSpec] = Field(max_length=50)
    rubric: list[RubricCriterion] = Field(min_length=1, max_length=12)
    max_score: float = Field(default=10, gt=0, le=100)
    due_at: datetime | None = None
    status: PracticalStatus = "draft"
    proctored: bool = True
    lockdown_mode: LockdownMode = "off"
    seb_config_key: str | None = Field(default=None, max_length=128)
    seb_config_url: str | None = Field(default=None, max_length=500)
    worksheet: WorksheetSpec | None = None  # required for worksheet labs; omitted on update = keep the current one

    @field_validator("seb_config_key")
    @classmethod
    def _config_key(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("SEB Config Key must be the 64-character hex value shown by SEB")
        return v

    @field_validator("seb_config_url")
    @classmethod
    def _config_url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        if not re.match(r"^(https?|sebs?)://", v.strip()):
            raise ValueError("SEB config URL must start with https://, http://, sebs:// or seb://")
        return v.strip()

    @field_validator("starter_files")
    @classmethod
    def _validate_files(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_files(v)


# ---------------------------------------------------------------- student workspace
class FilesBody(BaseModel):
    files: dict[str, str]

    @field_validator("files")
    @classmethod
    def _validate_files(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_files(v)


class RunRequest(FilesBody):
    mode: Literal["run", "test"] = "test"


class LintRequest(FilesBody):
    filename: str | None = None


class LintDiagnostic(BaseModel):
    line: int
    column: int = 1
    severity: Literal["error", "warning", "info"]
    message: str
    source: Literal["syntax", "gemma", "circuit"]


class LintResponse(BaseModel):
    diagnostics: list[LintDiagnostic]
    model: str
    cached: bool = False


class HintRequest(BaseModel):
    question: str | None = Field(default=None, max_length=1000)


class HintResponse(BaseModel):
    hint: str
    guiding_question: str | None = None
    concept: str | None = None
    hint_level: int
    max_hint_level: int = 3
    focus_test: str | None = None
    model: str
    source: Literal["gemini", "fallback"]


class TutorRequest(BaseModel):
    """One turn with the AI Lab Tutor. History is never accepted from the browser: it is read server-side."""

    action: TutorAction = "chat"
    message: str | None = Field(default=None, max_length=2000)  # the guard trims it to 1000 characters
    test: str | None = Field(default=None, max_length=120)  # explain_test: which visible test


class TutorThreadOut(BaseModel):
    messages: list[TutorMessage]
    dropped: int = 0  # older messages no longer stored with the thread
    ai_enabled: bool
    remaining_today: int
    per_day: int


class TutorReplyOut(BaseModel):
    messages: list[TutorMessage]  # [the student's message, the tutor's reply]
    remaining_today: int


class TutorTranscriptOut(BaseModel):
    """Faculty view of a student's tutor conversation on one practical."""

    messages: list[TutorMessage]
    dropped: int = 0
    student_messages: int
    hints: int
    max_hint_level: int
    flagged: int  # student messages the guard flagged (injection, restricted data, asked for the solution)
    concept_checks: list[str]  # evaluations, oldest first: understood | partial | not_yet


class DraftSaved(BaseModel):
    saved_at: datetime


# ---------------------------------------------------------------- faculty
class ReviewRequest(BaseModel):
    faculty_score: float | None = Field(default=None, ge=0, le=100)
    faculty_comment: str | None = Field(default=None, max_length=4000)


class GenerateTestsRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    lab_type: LabType
    reference_code: str | None = Field(default=None, max_length=100_000)


class GenerateTestsResponse(BaseModel):
    test_cases: list[TestCaseSpec]
    model: str
    source: Literal["gemini", "fallback"]


class TemplateOut(BaseModel):
    description: str
    starter_files: dict[str, str]
    test_cases: list[TestCaseSpec]
    rubric: list[RubricCriterion]
    worksheet: WorksheetSpec | None = None


# ---------------------------------------------------------------- HOD
class AssignFacultyRequest(BaseModel):
    faculty_id: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskTable(BaseModel):
    columns: list[str]
    rows: list[list[str | float | int]]


class AskResponse(BaseModel):
    answer: str
    highlights: list[str] = Field(default_factory=list)
    table: AskTable | None = None
    model: str
    source: Literal["gemini", "fallback"]


# ---------------------------------------------------------------- AI teaching assistant (faculty)
Difficulty = Literal["beginner", "intermediate", "advanced"]


class GeneratePracticalRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    course_id: str | None = None
    difficulty: Difficulty = "intermediate"
    duration_minutes: int = Field(default=120, ge=30, le=240)
    notes: str = Field(default="", max_length=1000)


class PracticalVerification(BaseModel):
    """The generated tests run in the sandbox against the generated reference solution and the starter code."""

    verified: bool  # every kept test passes on the reference solution and fails on the starter
    tests_total: int
    reference_passed: int
    starter_failed: int
    dropped: list[str] = Field(default_factory=list)  # tests removed: fail on the reference, or pass on the starter
    attempts: int = 1
    note: str | None = None


class GeneratedPracticalOut(BaseModel):
    title: str
    description: str  # markdown, lab-manual layout
    starter_files: dict[str, str]
    test_cases: list[TestCaseSpec]
    rubric: list[RubricCriterion]
    max_score: float = 10
    viva_questions: list[str]
    reference_files: dict[str, str]  # for the faculty member only (Validate); never stored with the practical
    verification: PracticalVerification
    model: str
    source: Literal["gemini"]


class TeachingMaterialRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    course_id: str | None = None
    level: Difficulty = "intermediate"
    duration_minutes: int = Field(default=60, ge=15, le=180)
    notes: str = Field(default="", max_length=1000)


class MaterialSection(BaseModel):
    heading: str
    content: str


class VivaItem(BaseModel):
    question: str
    answer: str


class TeachingMaterialOut(BaseModel):
    title: str
    overview: str
    learning_outcomes: list[str]
    sections: list[MaterialSection]
    examples: list[MaterialSection]
    real_world_examples: list[str]
    common_mistakes: list[str]
    discussion_questions: list[str]
    viva_questions: list[VivaItem]
    markdown: str  # the whole document, for download
    model: str
    source: Literal["gemini"]


# ---------------------------------------------------------------- AI department intelligence (HOD; faculty for own courses)
class DifficultyOut(BaseModel):
    concept: str
    explanation: str
    recommended_action: str
    practical_id: str
    practical_title: str
    tests: list[str]
    students_affected: int   # computed from the data, never by the model
    students_attempted: int
    fail_rate: float
    hint_requests: int
    example_questions: list[str] = Field(default_factory=list)


class CourseDifficultiesOut(BaseModel):
    course_id: str
    course_code: str
    course_title: str
    faculty_name: str | None
    difficulties: list[DifficultyOut]


class LearningDifficultiesOut(BaseModel):
    generated_at: datetime
    courses: list[CourseDifficultiesOut]
    model: str
    source: Literal["gemini", "fallback"]
    cached: bool = False


class BriefingAction(BaseModel):
    action: str
    owner: str
    reason: str


class DepartmentBriefingOut(BaseModel):
    period_start: datetime
    period_end: datetime
    headline: str
    highlights: list[str]
    concerns: list[str]
    actions: list[BriefingAction]
    metrics: dict  # the computed numbers the briefing is based on (shown beside it)
    markdown: str
    generated_at: datetime
    model: str
    source: Literal["gemini", "fallback"]
