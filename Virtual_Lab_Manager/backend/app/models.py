"""Domain records persisted by the repository layer (mirrors database/001_schema.sql)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["student", "faculty", "hod"]
LabType = Literal["coding", "circuit", "notebook", "worksheet"]
PracticalStatus = Literal["draft", "published"]
LockdownMode = Literal["off", "exam", "seb"]  # off: record only | exam: strict web exam | seb: exam + Safe Exam Browser
ExamStatus = Literal["active", "paused", "locked", "submitted"]
SubmissionStatus = Literal["graded", "reviewed"]

LAB_LANGUAGE: dict[str, str] = {
    "coding": "python",
    "circuit": "circuit-sim",
    "notebook": "python-notebook",
    "worksheet": "worksheet",
}
LAB_FILENAME: dict[str, str] = {
    "coding": "main.py",
    "circuit": "circuit.sim",
    "notebook": "data.ipynb",
    "worksheet": "answers.json",
}


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- value objects
class TestCaseSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    hidden: bool = False
    code: str | None = None  # coding / notebook
    inputs: dict[str, int] | None = None  # circuit
    expected: dict[str, int] | None = None  # circuit


# ---------------------------------------------------------------- worksheet labs (maths problems, virtual experiments)
# The student fills answers.json = {"steps": {step_id: "value"}, "rows": [{column_key: value}]}; the checks are
# ordinary hidden-code test cases run by the sandbox against that JSON (app/execution/service.py WorksheetAdapter).
_KEY = r"^[A-Za-z0-9_]+$"


class WorksheetStep(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=_KEY)
    label: str = Field(min_length=1, max_length=300)  # inline markdown, e.g. "x₁ = x₀ − f(x₀) / f′(x₀)"
    unit: str = Field(default="", max_length=20)
    placeholder: str = Field(default="", max_length=40)  # e.g. "4 decimal places"
    test: str | None = None  # name of the test case that checks this step


class WorksheetColumn(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=_KEY)
    label: str = Field(min_length=1, max_length=60)
    unit: str = Field(default="", max_length=20)
    source: Literal["apparatus", "student"] = "student"  # apparatus = recorded from the virtual instrument
    test: str | None = None


class WorksheetTable(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    columns: list[WorksheetColumn] = Field(min_length=1, max_length=8)
    min_rows: int = Field(default=5, ge=1, le=20)
    max_rows: int = Field(default=10, ge=1, le=20)
    test: str | None = None  # checks the recorded readings


class WorksheetGraph(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    x: str  # column keys
    y: str
    x_label: str
    y_label: str


class WorksheetSection(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=_KEY)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(default="", max_length=4000)  # markdown
    visual: Literal["newton", "simpson"] | None = None  # interactive figure drawn from the student's answers
    steps: list[WorksheetStep] = Field(default_factory=list, max_length=20)


class WorksheetSpec(BaseModel):
    kind: Literal["problems", "experiment"] = "problems"
    apparatus: Literal["pendulum", "dc_bench"] | None = None  # virtual instrument rendered above the table
    apparatus_config: dict[str, float] = Field(default_factory=dict)  # e.g. {"resistance_ohm": 220}
    table: WorksheetTable | None = None
    graph: WorksheetGraph | None = None
    sections: list[WorksheetSection] = Field(default_factory=list, max_length=10)


class RubricCriterion(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    max_points: float = Field(gt=0, le=100)


class TestResult(BaseModel):
    name: str
    passed: bool
    message: str | None = None
    hidden: bool = False


class RubricScore(BaseModel):
    criterion_id: str
    name: str
    score: float
    max_points: float
    feedback: str = ""


# ---------------------------------------------------------------- proctoring / integrity
ProctorEventType = Literal[
    "session_start", "paste_blocked", "copy_blocked", "cut_blocked", "drop_blocked", "context_menu_blocked",
    "devtools_blocked", "focus_lost", "fullscreen_exit", "large_insertion", "typing_stats",
    "exam_locked", "exam_unlocked",
    "break_start", "break_end",  # Pause button: a declared break (exam breaks are recorded by the server)
]
SERVER_EVENT_TYPES = {"typing_stats", "exam_locked", "exam_unlocked"}
CLIENT_EVENT_TYPES = set(ProctorEventType.__args__) - SERVER_EVENT_TYPES  # type: ignore[attr-defined]


class IntegritySignal(BaseModel):
    key: str
    label: str
    detail: str
    severity: Literal["info", "warning", "critical"]
    weight: int


class ProctoringStats(BaseModel):
    proctored: bool = True
    sessions: int = 0
    paste_blocked: int = 0
    copy_blocked: int = 0
    focus_lost: int = 0
    time_away_ms: int = 0
    fullscreen_exits: int = 0
    devtools_blocked: int = 0
    large_insertions: int = 0
    typed_chars: int = 0
    new_code_chars: int = 0
    typed_ratio: float | None = None
    max_burst_cps: float = 0


class ContentAnalysis(BaseModel):
    ai_style_score: int = 0
    indicators: list[str] = Field(default_factory=list)
    model: str = "rules"
    source: Literal["gemini", "fallback"] = "fallback"


class SimilarityResult(BaseModel):
    max_peer_similarity: float = 0
    peer_submission_id: str | None = None
    peer_student_name: str | None = None


class IntegrityReport(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    risk_score: int
    ai_likelihood: int
    summary: str
    signals: list[IntegritySignal]
    proctoring: ProctoringStats
    content: ContentAnalysis
    similarity: SimilarityResult
    analyzed_at: datetime = Field(default_factory=utcnow)


class ProctorSessionRecord(BaseModel):
    id: str  # client-generated uuid per page load
    practical_id: str
    student_id: str
    baseline_files: dict[str, str] = Field(default_factory=dict)  # captured server-side at session start
    stats: dict = Field(default_factory=dict)  # latest cumulative TypingStats
    started_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)


class ExamAttemptRecord(BaseModel):
    """Server-side lockdown state of one student's exam on one practical."""

    id: str = Field(default_factory=new_id)
    practical_id: str
    student_id: str
    status: ExamStatus = "active"
    active_session_id: str | None = None  # the only browser tab allowed to work; None after a mentor unlock
    last_session_id: str | None = None
    lock_reason: str | None = None
    violations: int = 0
    unlock_count: int = 0
    started_at: datetime = Field(default_factory=utcnow)
    last_heartbeat_at: datetime | None = None
    locked_at: datetime | None = None
    unlocked_at: datetime | None = None
    unlocked_by: str | None = None
    submitted_at: datetime | None = None
    paused_at: datetime | None = None  # set while the student is on a declared break (status "paused")
    breaks_used: int = 0
    break_ms: int = 0  # total length of finished breaks


class ProctorEventRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    practical_id: str
    student_id: str
    session_id: str
    event_type: ProctorEventType
    detail: dict = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------- records
class Department(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    code: str
    institution_name: str
    created_at: datetime = Field(default_factory=utcnow)


class UserRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    email: str
    password_hash: str
    full_name: str
    role: Role
    department_id: str
    roll_number: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class CourseRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    department_id: str
    code: str
    title: str
    semester: int
    faculty_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class PracticalRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    course_id: str
    title: str
    description: str
    lab_type: LabType
    language: str
    starter_files: dict[str, str]
    test_cases: list[TestCaseSpec]
    rubric: list[RubricCriterion]
    max_score: float = 10
    due_at: datetime | None = None
    status: PracticalStatus = "draft"
    proctored: bool = True
    lockdown_mode: LockdownMode = "off"
    seb_config_key: str | None = None  # SHA-256 hex Config Key of the SEB exam config — never sent to students
    seb_config_url: str | None = None  # where the .seb file is hosted (students get a seb:// / sebs:// launch link)
    worksheet: WorksheetSpec | None = None  # worksheet labs only
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SubmissionRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    practical_id: str
    student_id: str
    files: dict[str, str]
    status: SubmissionStatus = "graded"
    tests_passed: int = 0
    tests_total: int = 0
    test_results: list[TestResult] = Field(default_factory=list)
    rubric_score: float | None = None
    max_score: float = 10
    rubric_breakdown: list[RubricScore] = Field(default_factory=list)
    ai_feedback: str | None = None
    grading_model: str | None = None
    faculty_score: float | None = None
    faculty_comment: str | None = None
    integrity: IntegrityReport | None = None
    submitted_at: datetime = Field(default_factory=utcnow)
    graded_at: datetime | None = None
    reviewed_at: datetime | None = None

    @property
    def final_score(self) -> float | None:
        return self.faculty_score if self.faculty_score is not None else self.rubric_score


class ExecutionLogRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    practical_id: str
    student_id: str
    lab_type: LabType
    mode: Literal["run", "test"]
    engine: str
    status: str
    files: dict[str, str]
    stdout: str = ""
    stderr: str = ""
    test_results: list[TestResult] = Field(default_factory=list)
    tests_passed: int = 0
    tests_total: int = 0
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class HintLogRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    practical_id: str
    student_id: str
    execution_id: str | None = None
    focus_test: str | None = None
    hint_level: int = 1
    question: str | None = None
    hint_text: str
    model: str
    source: str
    created_at: datetime = Field(default_factory=utcnow)


TutorAction = Literal["chat", "explain_error", "explain_test", "explain_concept", "next_hint", "concept_check"]
Understanding = Literal["understood", "partial", "not_yet"]


class TutorMessage(BaseModel):
    """One turn of the AI Lab Tutor conversation (app/ai/tutor_chat.py)."""

    id: str = Field(default_factory=new_id)
    role: Literal["student", "tutor"]
    action: TutorAction = "chat"
    content: str
    guiding_question: str | None = None
    concept: str | None = None
    hint_level: int | None = None   # next_hint replies
    focus_test: str | None = None   # visible test the reply is about
    understanding: Understanding | None = None  # concept-check evaluation of the student's answer
    expects_answer: bool = False  # a concept-check question: the student's next chat message is the answer
    # guard / validator findings for the faculty transcript: injection, restricted, solution_request,
    # off_topic, code_removed, value_hidden, leak_blocked
    flags: list[str] = Field(default_factory=list)
    model: str | None = None
    source: Literal["gemini", "fallback", "guard"] | None = None
    execution_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TutorThreadRecord(BaseModel):
    """A student's tutor conversation on one practical. The browser never supplies history: it is read from here."""

    practical_id: str
    student_id: str
    messages: list[TutorMessage] = Field(default_factory=list)
    dropped: int = 0  # oldest messages removed to keep one Firestore document well under 1 MiB
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DraftRecord(BaseModel):
    practical_id: str
    student_id: str
    files: dict[str, str]
    updated_at: datetime = Field(default_factory=utcnow)
