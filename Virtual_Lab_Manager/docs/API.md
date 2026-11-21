# Virtual Lab Manager — API Contract (v1)

Base URL: `${NEXT_PUBLIC_API_URL}` (default `http://localhost:8000`). All routes are prefixed with `/api`.
Auth: `Authorization: Bearer <access_token>` (JWT, HS256). Errors use FastAPI's shape: `{ "detail": string }`.
All timestamps are ISO‑8601 UTC strings. All IDs are UUID strings. Scores are numbers (1 decimal).

## Shared types (TypeScript notation)

```ts
type Role = "student" | "faculty" | "hod";
type LabType = "coding" | "circuit" | "notebook" | "worksheet";  // main.py | circuit.sim | data.ipynb | answers.json

interface User {
  id: string; email: string; full_name: string; role: Role;
  department_id: string; roll_number: string | null;
}

interface Course {
  id: string; code: string; title: string; semester: number;
  department_id: string; faculty_id: string | null; faculty_name: string | null;
  enrolled: number;                                    // enrolled student count
}

// Faculty-facing test spec. Students only receive tests with hidden=false.
interface TestCaseSpec {
  name: string;                 // e.g. "test_duplicate_keys"
  description: string;
  hidden: boolean;
  code?: string | null;         // coding/notebook: Python statements with asserts, run in the student's namespace
  inputs?: Record<string, number> | null;    // circuit: {"A":0,"B":1}
  expected?: Record<string, number> | null;  // circuit: {"SUM":1,"CARRY":0}
}

interface RubricCriterion { id: string; name: string; description: string; max_points: number; }

interface Practical {
  id: string; course_id: string; course_code: string; course_title: string;
  title: string;
  description: string;                       // markdown
  lab_type: LabType;
  language: string;                          // "python" | "circuit-sim" | "python-notebook" | "worksheet"
  starter_files: Record<string, string>;     // { "main.py": "..." } | { "circuit.sim": "..." } | { "data.ipynb": "<nbformat JSON string>" }
  test_cases: TestCaseSpec[];                // students: visible tests only (worksheet labs: code is null)
  worksheet?: WorksheetSpec | null;          // worksheet labs: what the worksheet renders (see File formats)
  hidden_test_count: number;
  rubric: RubricCriterion[];
  max_score: number;                         // default 10
  due_at: string | null;
  status: "draft" | "published";
  created_at: string;
}

// Student practical detail additionally carries their saved draft + latest submission
interface StudentPractical extends Practical {
  draft_files: Record<string, string> | null;   // null => use starter_files
  draft_updated_at: string | null;
  latest_submission: Submission | null;
  hints_used: number;
  submission_limit: number;   // submissions allowed per student (an exam ends at its first submission)
  submissions_used: number;
}

interface TestResult {
  name: string; passed: boolean; message: string | null; hidden: boolean;
}

interface CellOutput { index: number; stdout: string; error: string | null; }        // notebook only
interface TruthTableRow { inputs: Record<string, number>; outputs: Record<string, number>; }  // circuit only

interface ExecutionResult {
  execution_id: string | null;
  engine: string;              // "judge0" | "local-python" | "circuit-sim"
  lab_type: LabType;
  mode: "run" | "test";
  status: "ok" | "error" | "timeout" | "compile_error";
  stdout: string; stderr: string;
  tests: TestResult[];         // empty for mode=run
  tests_passed: number; tests_total: number;
  duration_ms: number;
  cell_outputs: CellOutput[] | null;
  truth_table: TruthTableRow[] | null;
  summary: string;             // e.g. "4 of 5 Tests Passed"
}

interface LintDiagnostic {
  line: number; column: number;              // 1-based
  severity: "error" | "warning" | "info";
  message: string;
  source: "syntax" | "gemma" | "circuit";
}
interface LintResponse { diagnostics: LintDiagnostic[]; model: string; cached: boolean; }

interface HintResponse {
  hint: string;                              // markdown, never contains full solution code
  guiding_question: string | null;
  concept: string | null;                    // e.g. "BST invariant for equal keys"
  hint_level: number;                        // 1..3 (progressive)
  max_hint_level: number;                    // 3
  focus_test: string | null;                 // e.g. "test_duplicate_keys"
  model: string;
  source: "gemini" | "fallback";
}

interface RubricScore { criterion_id: string; name: string; score: number; max_points: number; feedback: string; }

interface Submission {
  id: string; practical_id: string; practical_title: string; course_code: string;
  lab_type: LabType;
  student_id: string; student_name: string; roll_number: string | null;
  files: Record<string, string>;
  status: "graded" | "reviewed";
  tests_passed: number; tests_total: number; test_results: TestResult[];
  rubric_score: number | null; max_score: number;
  rubric_breakdown: RubricScore[];
  ai_feedback: string | null;
  grading_model: string | null;
  faculty_score: number | null; faculty_comment: string | null;
  final_score: number | null;                // faculty_score ?? rubric_score
  submitted_at: string; graded_at: string | null; reviewed_at: string | null;
}
```

## Health
- `GET /api/health` → `{ status: "ok", storage: "memory" | "postgres", execution_engine: string, ai: { gemini_model: string, gemma_model: string, enabled: boolean } }`

## Auth
- `POST /api/auth/login` body `{ email, password }` → `{ access_token: string, token_type: "bearer", user: User }` (401 on bad creds)
- `GET /api/auth/me` → `User`
- `GET /api/auth/demo-accounts` → `{ role: Role, email: string, full_name: string, password: string }[]` (empty array when demo mode is off)

## Student (role=student)
- `GET /api/student/dashboard` →
  ```ts
  {
    user: User;
    courses: Course[];
    practicals: {
      id: string; title: string; course_id: string; course_code: string; course_title: string;
      lab_type: LabType; due_at: string | null; max_score: number;
      progress: "not_started" | "in_progress" | "submitted" | "graded";
      best_score: number | null; attempts: number; last_activity_at: string | null;
    }[];
    stats: { assigned: number; completed: number; avg_score: number | null; hints_used: number };
    recent_submissions: Submission[];
  }
  ```
- `GET /api/student/practicals/{id}` → `StudentPractical`
- `PUT /api/student/practicals/{id}/draft` body `{ files: Record<string,string> }` → `{ saved_at: string }`
- `POST /api/student/practicals/{id}/run` body `{ files, mode: "run" | "test" }` → `ExecutionResult` (only visible tests are run)
- `POST /api/student/practicals/{id}/lint` body `{ files, filename }` → `LintResponse`
- `POST /api/student/practicals/{id}/hint` body `{ question?: string }` → `HintResponse` (uses the student's latest test run on the server)
- `POST /api/student/practicals/{id}/submit` body `{ files }` → `Submission` (runs visible + hidden tests, AI rubric grading)
- `GET /api/student/submissions` → `Submission[]`

## Faculty (role=faculty; HOD may also call)
- `GET /api/faculty/dashboard` →
  ```ts
  {
    courses: Course[];
    practicals: {
      id: string; title: string; course_id: string; course_code: string; lab_type: LabType;
      status: "draft" | "published"; due_at: string | null; max_score: number;
      enrolled: number; submitted: number; avg_score: number | null; pass_rate: number | null;  // pass_rate 0..100
    }[];
    recent_submissions: Submission[];
    stats: { courses: number; practicals: number; submissions: number; pending_review: number; avg_score: number | null };
  }
  ```
- `GET /api/faculty/templates/{lab_type}` → `{ description: string; starter_files: Record<string,string>; test_cases: TestCaseSpec[]; rubric: RubricCriterion[]; worksheet?: WorksheetSpec }`
- `POST /api/faculty/practicals` body `PracticalInput` → `Practical`
- `GET /api/faculty/practicals/{id}` → `Practical` (includes hidden tests)
- `PUT /api/faculty/practicals/{id}` body `PracticalInput` → `Practical`
- `POST /api/faculty/practicals/{id}/publish` → `Practical`
- `POST /api/faculty/practicals/{id}/validate` body `{ files }` → `ExecutionResult` (runs ALL tests incl. hidden against e.g. a reference solution)
- `GET /api/faculty/practicals/{id}/submissions` → `Submission[]`
- `GET /api/faculty/submissions/{id}` → `Submission`
- `POST /api/faculty/submissions/{id}/review` body `{ faculty_score?: number | null, faculty_comment?: string | null }` → `Submission`
- `POST /api/faculty/ai/generate-tests` body `{ title, description, lab_type, reference_code?: string }` → `{ test_cases: TestCaseSpec[], model: string, source: "gemini" | "fallback" }`

```ts
interface PracticalInput {
  course_id: string; title: string; description: string; lab_type: LabType;
  starter_files: Record<string, string>; test_cases: TestCaseSpec[]; rubric: RubricCriterion[];
  max_score: number; due_at: string | null; status: "draft" | "published";
}
```

## HOD (role=hod)
- `GET /api/hod/overview` →
  ```ts
  {
    department: { id: string; name: string; code: string; institution_name: string };
    kpis: {
      students: number; faculty: number; courses: number; practicals: number; submissions: number;
      completion_rate: number;        // 0..100
      avg_score_pct: number | null;   // 0..100
      at_risk_students: number; ai_hints_served: number;
    };
    courses: {
      id: string; code: string; title: string; semester: number;
      faculty_id: string | null; faculty_name: string | null;
      enrolled: number; practicals: number; submissions: number;
      completion_rate: number; avg_score_pct: number | null;
    }[];
    bottlenecks: {
      practical_id: string; practical_title: string; course_code: string; test_name: string;
      fail_count: number; attempts: number; fail_rate: number; hint_requests: number;
    }[];
    at_risk: { student_id: string; student_name: string; roll_number: string | null; completion_rate: number; avg_score_pct: number | null }[];
    activity: { date: string; executions: number; submissions: number; hints: number }[];   // last 14 days, YYYY-MM-DD
    score_distribution: { bucket: string; count: number }[];                                // "0-20","20-40",...,"80-100" (percent)
  }
  ```
- `GET /api/hod/faculty` → `{ id: string; full_name: string; email: string; courses: string[] }[]`
- `PUT /api/hod/courses/{id}/faculty` body `{ faculty_id: string }` → `Course`
- `GET /api/hod/compliance-report` → `{ generated_at: string; department: string; rows: ComplianceRow[] }`
- `GET /api/hod/compliance-report?format=csv` → `text/csv` attachment
  ```ts
  interface ComplianceRow {
    course_code: string; course_title: string; faculty_name: string | null; practical_title: string;
    due_at: string | null; enrolled: number; submitted: number; completion_rate: number;
    avg_score_pct: number | null; status: "compliant" | "at_risk" | "non_compliant";
  }
  ```
- `POST /api/hod/ask` body `{ question: string }` →
  `{ answer: string; highlights: string[]; table: { columns: string[]; rows: (string | number)[][] } | null; model: string; source: "gemini" | "fallback" }`

## File formats
- **main.py** — plain Python 3. Tests run in the student's module namespace (`__name__ != "__main__"`).
- **circuit.sim** — line-based netlist:
  ```
  # Half adder
  INPUT A B
  OUTPUT SUM CARRY
  SUM = XOR(A, B)
  CARRY = AND(A, B)
  ```
  Gates: `AND OR NOT XOR NAND NOR XNOR BUF` (n-ary except NOT/BUF), nesting allowed, intermediate wires allowed (`W1 = AND(A, B)`), literals `0`/`1`.
- **answers.json** (worksheet labs) — `{ "steps": { [stepId]: string }, "rows": [{ [columnKey]: string | number }] }`.
  Steps hold what the student typed; rows are the observation table (instrument readings are numbers, typed cells
  strings). The layout comes from `Practical.worksheet`:
  ```ts
  interface WorksheetSpec {
    kind: "problems" | "experiment";
    apparatus: "pendulum" | "dc_bench" | null;       // virtual instrument above the table
    apparatus_config: Record<string, number>;        // e.g. { resistance_ohm: 220, rated_power_w: 0.5 }
    table: { title; columns: { key; label; unit; source: "apparatus" | "student"; test }[]; min_rows; max_rows; test } | null;
    graph: { title; x; y; x_label; y_label } | null; // scatter + least-squares line of two table columns
    sections: { id; title; body; visual: "newton" | "simpson" | null; steps: { id; label; unit; placeholder; test }[] }[];
  }
  ```
  Each step / column / table names the test that checks it. Checks are Python assertions run in the sandbox with
  helpers `answer(id)`, `column(key)`, `readings(n)`, `near`, `near_rel`, `fit_line`; the answers are embedded as a JSON
  string literal, never executed. Faculty can create worksheet labs through the API (`worksheet` in the practical body);
  the practical form edits everything except the layout, which an update keeps when it is omitted.
- **data.ipynb** — nbformat‑4 JSON string: `{ "nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [{ "cell_type": "markdown" | "code", "source": string, "metadata": {}, "outputs": [], "execution_count": null }] }`. Code cells execute top‑to‑bottom in one shared namespace (standard library only).

## Demo accounts (demo mode, password `demo1234`)
- student: `aarav.sharma@demo.edu` (Lab 4: Binary Search Trees draft pre-loaded, fails `test_duplicate_keys`)
- faculty: `meera.kulkarni@demo.edu`
- hod: `rajesh.deshpande@demo.edu`

---

# v1.1 — Proctoring & Academic Integrity

## Changed types
```ts
interface Practical { /* ...v1 fields... */ proctored: boolean; }            // default true
interface PracticalInput { /* ...v1 fields... */ proctored: boolean; }       // default true
interface StudentPractical { /* ...v1 fields... */ proctoring_summary: ProctorSummary | null; } // null when not proctored
interface Submission { /* ...v1 fields... */ integrity: IntegrityReport | null; } // ALWAYS null in student endpoints
HodOverview.kpis.integrity_flags: number   // submissions with integrity risk medium or high
```

## New types
```ts
type ProctorEventType =
  | "session_start"            // student clicked "Start proctored session" (server attaches baseline code)
  | "paste_blocked" | "copy_blocked" | "cut_blocked" | "drop_blocked" | "context_menu_blocked"
  | "devtools_blocked"         // F12 / Ctrl+Shift+I/J/C / Cmd+Opt+I/J/C / Ctrl+U intercepted
  | "focus_lost"               // detail: { duration_ms: number, reason: "tab_hidden" | "window_blur" } — sent when focus returns
  | "fullscreen_exit"
  | "large_insertion";         // detail: { chars: number } — single editor change >= 60 chars (not undo/redo/load)

interface ProctorEventIn { type: ProctorEventType; at: string; detail?: Record<string, string | number | boolean> }

interface TypingStats {            // cumulative for the current page session
  typed_chars: number;             // chars inserted by in-editor edits < 60 chars (excl. undo/redo/load)
  keystrokes: number;
  active_ms: number;               // sum of gaps between edits that are < 30 s
  large_insertions: number;
  large_insertion_chars: number;
  max_burst_cps: number;           // max chars/sec over any 2 s window
}

interface ProctorSummary {         // all sessions of this student for this practical
  sessions: number; paste_blocked: number; copy_blocked: number; focus_lost: number;
  time_away_ms: number; fullscreen_exits: number; devtools_blocked: number; large_insertions: number;
}

interface IntegritySignal {
  key: string;                     // e.g. "typed_ratio", "ai_style", "peer_similarity", "no_session"
  label: string;                   // short title
  detail: string;                  // human explanation with numbers
  severity: "info" | "warning" | "critical";
  weight: number;                  // contribution to risk_score
}

interface IntegrityReport {
  risk_level: "low" | "medium" | "high";
  risk_score: number;              // 0..100 overall integrity risk
  ai_likelihood: number;           // 0..100 likelihood code is AI-generated / externally sourced
  summary: string;
  signals: IntegritySignal[];      // sorted by weight desc
  proctoring: {
    proctored: boolean; sessions: number; paste_blocked: number; copy_blocked: number; focus_lost: number;
    time_away_ms: number; fullscreen_exits: number; devtools_blocked: number; large_insertions: number;
    typed_chars: number; new_code_chars: number; typed_ratio: number | null; max_burst_cps: number;
  };
  content: { ai_style_score: number; indicators: string[]; model: string; source: "gemini" | "fallback" };
  similarity: { max_peer_similarity: number; peer_submission_id: string | null; peer_student_name: string | null };
  analyzed_at: string;
}

interface ProctorEventOut {
  id: string; session_id: string; type: ProctorEventType | "typing_stats";
  detail: Record<string, unknown>; occurred_at: string; created_at: string;
}
```

## New endpoints
- `POST /api/student/practicals/{id}/proctor/events` (student) body
  `{ session_id: string (uuid), events: ProctorEventIn[] (max 100), stats?: TypingStats | null }`
  → `{ accepted: number, summary: ProctorSummary }`
- `GET /api/faculty/submissions/{id}/proctor-events` (faculty/hod) → `ProctorEventOut[]` (timeline for that student + practical, oldest first, `typing_stats` rows included)

Integrity is computed at submit time and is visible to faculty/HOD only. It is an indicator for review, not proof.

---

# v1.2 — Exam Lockdown (strict web exam mode + Safe Exam Browser) & Live Lab Monitor

Browsers cannot close other tabs/apps, so lockdown is enforced **server-side**: one browser tab (the
"exam session") may work on an exam; leaving it locks the exam; only a mentor can unlock.

## Changed types
```ts
type LockdownMode = "off" | "exam" | "seb";   // off: proctoring only | exam: strict web exam | seb: exam + Safe Exam Browser
interface Practical { /* ... */ lockdown_mode: LockdownMode; seb_config_url: string | null; seb_launch_url: string | null;
                      seb_config_key: string | null /* faculty/HOD responses only; always null for students */ }
interface PracticalInput { /* ... */ lockdown_mode: LockdownMode; seb_config_key?: string | null /* 64-hex, required for "seb" */;
                           seb_config_url?: string | null /* https://…/exam.seb */ }
interface StudentPractical { /* ... */ exam: ExamState | null }   // null when lockdown_mode === "off"
type ProctorEventType = /* v1.1 types */ | "exam_locked" | "exam_unlocked";  // server-generated only (timeline)

interface ExamState {
  lockdown_mode: LockdownMode;
  status: "not_started" | "active" | "locked" | "submitted";
  lock_reason: string | null; violations: number; locked_at: string | null;
  is_current_session: boolean;     // this tab (session_id) holds the exam
  awaiting_resume: boolean;        // a mentor unlocked: call /exam/start again with this tab's session_id
  seb_required: boolean; seb_verified: boolean;
}
```

## Student endpoints (lockdown practicals)
- `POST /api/student/practicals/{id}/exam/start` `{ session_id }` → `ExamState`. Claims the exam for this tab (use the SAME uuid as the proctoring `session_id`). A second tab while the first is alive, or a new tab after the page was closed/reloaded, **locks** the exam.
- `POST /api/student/practicals/{id}/exam/heartbeat` `{ session_id }` → `ExamState` — call every ~5 s; detects mentor unlock (`awaiting_resume`) or lock.
- `POST /api/student/practicals/{id}/exam/violation` `{ session_id, type: "focus_lost" | "fullscreen_exit" | "devtools_blocked" | "second_tab" | "page_closed", detail? }` → `ExamState` (locks immediately; ignored while paused).
- `POST /api/student/practicals/{id}/exam/pause` `{ session_id }` → `ExamState` with `status: "paused"` — Pause button. Only the tab holding an
  active exam; at most `max_breaks` (2) per exam, else 409. While paused, enforced calls return 423 and leaving / closing the
  page is not a violation. A break longer than `break_limit_s` (600) locks the exam ("Break ran over the 10-minute limit").
- `POST /api/student/practicals/{id}/exam/resume` `{ session_id }` → `ExamState` — ends the break and gives the exam to this tab
  (it may be a new tab). `ExamState` also carries `paused_at, breaks_used, max_breaks, break_limit_s`; monitor rows carry
  `paused_at, breaks_used, break_ms`. Proctored (non-exam) labs record breaks client-side as `break_start` / `break_end` events;
  `ProctorSummary` has `breaks` and `break_ms`.
  Only the tab holding the exam (`session_id === active session`) can lock it; reports from other/stale tabs or an
  already-locked exam are ignored and not counted, so `violations` = number of locks caused by violations.
  `page_closed` (v1.2.1) is sent with `fetch(…, { keepalive: true })` on `pagehide` / leaving the page, so a reload
  shows "Left the exam page (closed, reloaded or navigated away)" instead of being treated as a second tab.
- **Every** `run`, `lint`, `hint`, `draft`, `submit` call on a lockdown practical must send header `X-Exam-Session: <session_id>`. Errors: `409` "Start the exam session first" / "active in another tab or window" / "already been submitted"; `423` "Exam locked: <reason>. Ask your mentor to unlock it."; `403` "must be taken in Safe Exam Browser".
- A successful submit ends the exam (`status: "submitted"`; further work → 409).
- **Safe Exam Browser (`lockdown_mode: "seb"`)**: when `window.SafeExamBrowser` exists, call `SafeExamBrowser.security.updateKeys(cb)` if present, then send on exam start/heartbeat AND all enforced calls:
  `X-SEB-Page-Url: <location.href without #fragment>` and `X-SEB-ConfigKey-Hash: <SafeExamBrowser.security.configKey>`.
  Outside SEB, show "This exam must be taken in Safe Exam Browser" with a button to `seb_launch_url` (if set).

## Faculty / HOD endpoints
- `GET /api/faculty/practicals/{id}/monitor` → `MonitorResponse` (poll every ~5 s)
- `POST /api/faculty/practicals/{id}/exam/{student_id}/unlock` → `MonitorRow`
- `POST /api/faculty/practicals/{id}/exam/{student_id}/lock` `{ reason?: string }` → `MonitorRow`
- `GET /api/faculty/alerts` → `{ locked_count: number; locked: LockAlert[] }` (poll every ~10 s for a notification bell)
- `GET /api/faculty/dashboard` — each `practicals[]` row also carries `proctored: boolean` and `lockdown_mode` (v1.2.1).

```ts
interface MonitorRow {
  student_id: string; student_name: string; roll_number: string | null;
  status: "not_started" | "active" | "locked" | "submitted"; online: boolean; last_seen_at: string | null;
  lock_reason: string | null; locked_at: string | null; violations: number; unlock_count: number;
  paste_blocked: number; copy_blocked: number; focus_lost: number; fullscreen_exits: number; time_away_ms: number;
  tests_passed: number | null; tests_total: number | null;       // latest test run
  submission_id: string | null; final_score: number | null; max_score: number;
  integrity_risk: "low" | "medium" | "high" | null;
}
interface MonitorResponse {
  practical_id: string; practical_title: string; course_code: string; lockdown_mode: LockdownMode; proctored: boolean;
  generated_at: string; counts: { not_started: number; active: number; locked: number; submitted: number; online: number };
  rows: MonitorRow[];              // locked first, then active (online first), not started, submitted
}
interface LockAlert { practical_id: string; practical_title: string; course_code: string; student_id: string;
                      student_name: string; roll_number: string | null; lock_reason: string | null; locked_at: string | null }
```
The monitor also works for proctored labs without lockdown (status derived from activity; no lock/unlock).

---

# v1.5 — AI Lab Tutor (scoped, conversational)

A tutor chat inside each lab (the workspace's **Tutor** drawer). It knows only the open lab and never gives the
solution. Pipeline and guardrails: `backend/app/ai/tutor_chat.py`, `.agents/skills/socratic-tutor/SKILL.md`.

## Types
```ts
type TutorAction = "chat" | "explain_error" | "explain_test" | "explain_concept" | "next_hint" | "concept_check";
interface TutorMessage {
  id: string; role: "student" | "tutor"; action: TutorAction;
  content: string;                       // markdown; tutor replies never contain solution code
  guiding_question: string | null; concept: string | null;
  hint_level: number | null;             // next_hint replies: 1..3 (same levels as POST /hint)
  focus_test: string | null;             // visible test the message is about
  understanding: "understood" | "partial" | "not_yet" | null;   // concept-check evaluation
  expects_answer: boolean;               // concept-check question: the next chat message is the answer
  flags: string[];                       // student: injection | restricted (+ hidden_tests | reference_solution | other_students) | solution_request
                                         // tutor:   code_removed | value_hidden | off_topic | leak_blocked
  model: string | null; source: "gemini" | "fallback" | "guard" | null;
  execution_id: string | null; created_at: string;
}
```

## Student endpoints
- `GET /api/student/practicals/{id}/tutor` → `{ messages: TutorMessage[]; dropped: number; ai_enabled: boolean; remaining_today: number; per_day: number }`
- `POST /api/student/practicals/{id}/tutor` body `{ action?: TutorAction = "chat"; message?: string (≤ 1000 used); test?: string }`
  → `{ messages: [studentMessage, tutorReply]; remaining_today: number }`
  - The conversation is stored server-side; the browser never sends history. The model gets the last 6 messages.
  - Uses the student's latest **server-side** test run (send `run` with mode `test` first if the code changed).
  - `next_hint` is the three-level Socratic hint (writes `ai_hint_logs`, shares levels with `POST /hint`).
  - `concept_check` only opens when every visible test passes; the student's next `chat` message is evaluated.
  - Exam lockdown: send `X-Exam-Session` like every other enforced call (409 / 423 / 403 as in v1.2).
  - `422` empty chat message · `429` more than 8 requests a minute or 60 a day per student per practical.

## Faculty endpoint
- `GET /api/faculty/submissions/{id}/tutor` → `{ messages: TutorMessage[]; dropped: number; student_messages: number; hints: number; max_hint_level: number; flagged: number; concept_checks: ("understood"|"partial"|"not_yet")[] }`
  (the submitting student's conversation on that practical; same access rules as the submission).

## What the model can and cannot see
| Context | Sent to Gemini |
|---|---|
| Lab title, brief, worksheet instructions (sections, step labels) | yes |
| The student's own current files / answers | yes |
| Visible test cases (worksheet checks: description only) and visible results, stderr | yes |
| Last 6 messages of the server-side conversation | yes |
| Hidden tests (code, names, results), rubric, worksheet check code (expected values), instrument constants, SEB keys | never |
| Other students' work, the faculty reference solution | never (not stored with the lab) |

---

# v1.6 — AI teaching assistant (faculty) & department intelligence (HOD)

Everything is a draft or a recommendation: nothing is saved, published or sent automatically.
Services: `backend/app/ai/{practical_gen,teaching,difficulties,briefing}.py`; evidence: `backend/app/services/insights.py`.

## Faculty (role faculty; HOD may also call)
- `POST /api/faculty/ai/generate-practical` body `{ topic: string (3-200); course_id?: string; difficulty?: "beginner"|"intermediate"|"advanced"; duration_minutes?: number; notes?: string }`
  → `GeneratedPractical { title; description (markdown: Aim, Objectives, Theory, Problem statement, Examples, Constraints, Viva questions); starter_files; test_cases; rubric (sums to 10); max_score; viva_questions; reference_files; verification; model; source: "gemini" }`
  - Coding labs. The generated tests are run in the sandbox against the generated reference solution (must pass) and the
    starter (must fail); failing / trivial tests are dropped, and one repair round is made if any test fails on the reference.
  - `verification = { verified, tests_total, reference_passed, starter_failed, dropped: string[], attempts, note }`.
  - `reference_files` is for the faculty member's Validate box only; it is never stored with the practical.
- `POST /api/faculty/ai/teaching-material` body `{ topic; course_id?; level?; duration_minutes?; notes? }`
  → `{ title; overview; learning_outcomes[]; sections[{heading, content}]; examples[{heading, content}]; real_world_examples[]; common_mistakes[]; discussion_questions[]; viva_questions[{question, answer}]; markdown; model; source }`
- `GET /api/faculty/ai/learning-difficulties?refresh=` → `LearningDifficulties` for the caller's courses.
- Both generators: `503` when Gemini isn't configured or returns nothing usable; `429` after 20 generations per user per hour; `403` for a course the faculty member doesn't teach.

## HOD (role hod)
- `GET /api/hod/ai/learning-difficulties?refresh=` → `LearningDifficulties` for the department (cached 15 min per scope; `cached: true` when served from cache).
  ```ts
  interface LearningDifficulty { concept; explanation; recommended_action; practical_id; practical_title; tests: string[];
    students_affected: number; students_attempted: number; fail_rate: number; hint_requests: number; example_questions: string[] }
  interface LearningDifficulties { generated_at; courses: { course_id; course_code; course_title; faculty_name; difficulties: LearningDifficulty[] }[];
    model; source: "gemini" | "fallback"; cached }
  ```
  Numbers are computed from executions, hint logs and tutor threads; Gemini only names, explains and recommends. Test names
  and example questions in its answer are checked against the evidence. Student questions are anonymised before they reach
  the model; questions the tutor's guard flagged are excluded.
- `POST /api/hod/ai/briefing` → `{ period_start; period_end; headline; highlights[]; concerns[]; actions[{action, owner, reason}]; metrics; markdown; generated_at; model; source }`.
  `metrics` (this week vs last week, pending reviews, practicals behind, at-risk count, unassigned courses, top bottlenecks) is
  what the narrative is based on; without Gemini the briefing is assembled from it by rules.
