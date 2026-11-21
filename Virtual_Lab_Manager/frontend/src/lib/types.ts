// Mirrors docs/API.md (v1, v1.1 proctoring, v1.2 exam lockdown). Keep in sync with the backend Pydantic schemas.

export type Role = "student" | "faculty" | "hod";
export type LabType = "coding" | "circuit" | "notebook" | "worksheet";

// ---------- worksheet labs (step-by-step maths, virtual experiments) ----------
export interface WorksheetStep {
  id: string;
  /** inline text with unicode maths, e.g. "x₁ = x₀ − f(x₀) / f′(x₀)" */
  label: string;
  unit: string;
  placeholder: string;
  /** test case that checks this step */
  test: string | null;
}
export interface WorksheetColumn {
  key: string;
  label: string;
  unit: string;
  /** apparatus = recorded from the virtual instrument (read-only), student = typed */
  source: "apparatus" | "student";
  test: string | null;
}
export interface WorksheetTable {
  title: string;
  columns: WorksheetColumn[];
  min_rows: number;
  max_rows: number;
  test: string | null;
}
export interface WorksheetGraph {
  title: string;
  x: string;
  y: string;
  x_label: string;
  y_label: string;
}
export interface WorksheetSection {
  id: string;
  title: string;
  body: string;
  visual: "newton" | "simpson" | null;
  steps: WorksheetStep[];
}
export interface WorksheetSpec {
  kind: "problems" | "experiment";
  apparatus: "pendulum" | "dc_bench" | null;
  apparatus_config: Record<string, number>;
  table: WorksheetTable | null;
  graph: WorksheetGraph | null;
  sections: WorksheetSection[];
}
/** answers.json: step answers as typed + observation rows (apparatus cells are numbers, typed cells strings) */
export type WorksheetCell = string | number | null;
export interface WorksheetAnswers {
  steps: Record<string, string>;
  rows: Record<string, WorksheetCell>[];
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  department_id: string;
  roll_number: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface DemoAccount {
  role: Role;
  email: string;
  full_name: string;
  password: string;
}

export interface Course {
  id: string;
  code: string;
  title: string;
  semester: number;
  department_id: string;
  faculty_id: string | null;
  faculty_name: string | null;
  enrolled: number;
}

export interface TestCaseSpec {
  name: string;
  description: string;
  hidden: boolean;
  code?: string | null;
  inputs?: Record<string, number> | null;
  expected?: Record<string, number> | null;
}

export interface RubricCriterion {
  id: string;
  name: string;
  description: string;
  max_points: number;
}

export type PracticalStatus = "draft" | "published";

export interface Practical {
  id: string;
  course_id: string;
  course_code: string;
  course_title: string;
  title: string;
  description: string;
  lab_type: LabType;
  language: string;
  starter_files: Record<string, string>;
  test_cases: TestCaseSpec[];
  hidden_test_count: number;
  rubric: RubricCriterion[];
  max_score: number;
  due_at: string | null;
  status: PracticalStatus;
  created_at: string;
  /** v1.1 — default true; may be missing on an older backend (treat as true). */
  proctored?: boolean;
  /** v1.2 — exam lockdown; missing on an older backend (treat as "off"). */
  lockdown_mode?: LockdownMode;
  seb_config_url?: string | null;
  /** sebs:// / seb:// link that opens the exam config in Safe Exam Browser */
  seb_launch_url?: string | null;
  /** faculty/HOD responses only — always null for students */
  seb_config_key?: string | null;
  /** worksheet labs only */
  worksheet?: WorksheetSpec | null;
}

export interface StudentPractical extends Practical {
  draft_files: Record<string, string> | null;
  draft_updated_at: string | null;
  latest_submission: Submission | null;
  hints_used: number;
  /** v1.1 — null when the practical is not proctored (may be missing on an older backend). */
  proctoring_summary?: ProctorSummary | null;
  /** v1.2 — null when lockdown_mode is "off". */
  exam?: ExamState | null;
  /** submissions allowed per student (an exam ends at its first submission); missing on an older backend */
  submission_limit?: number;
  submissions_used?: number;
}

export interface TestResult {
  name: string;
  passed: boolean;
  message: string | null;
  hidden: boolean;
}

export interface CellOutput {
  index: number;
  stdout: string;
  error: string | null;
}

export interface TruthTableRow {
  inputs: Record<string, number>;
  outputs: Record<string, number>;
}

export type ExecutionMode = "run" | "test";
export type ExecutionStatus = "ok" | "error" | "timeout" | "compile_error";

export interface ExecutionResult {
  execution_id: string | null;
  engine: string;
  lab_type: LabType;
  mode: ExecutionMode;
  status: ExecutionStatus;
  stdout: string;
  stderr: string;
  tests: TestResult[];
  tests_passed: number;
  tests_total: number;
  duration_ms: number;
  cell_outputs: CellOutput[] | null;
  truth_table: TruthTableRow[] | null;
  summary: string;
}

export interface LintDiagnostic {
  line: number;
  column: number;
  severity: "error" | "warning" | "info";
  message: string;
  source: "syntax" | "gemma" | "circuit";
}

export interface LintResponse {
  diagnostics: LintDiagnostic[];
  model: string;
  cached: boolean;
}

export interface HintResponse {
  hint: string;
  guiding_question: string | null;
  concept: string | null;
  hint_level: number;
  max_hint_level: number;
  focus_test: string | null;
  model: string;
  source: "gemini" | "fallback";
}

// ---------- AI Lab Tutor (v1.5) ----------
export type TutorAction = "chat" | "explain_error" | "explain_test" | "explain_concept" | "next_hint" | "concept_check";
export type Understanding = "understood" | "partial" | "not_yet";

export interface TutorMessage {
  id: string;
  role: "student" | "tutor";
  action: TutorAction;
  content: string;
  guiding_question: string | null;
  concept: string | null;
  hint_level: number | null;
  focus_test: string | null;
  understanding: Understanding | null;
  /** concept-check question: the student's next chat message is the answer */
  expects_answer: boolean;
  /** guard / validator findings (faculty view): injection, restricted, solution_request, off_topic, code_removed, value_hidden, leak_blocked */
  flags: string[];
  model: string | null;
  source: "gemini" | "fallback" | "guard" | null;
  execution_id: string | null;
  created_at: string;
}

export interface TutorThread {
  messages: TutorMessage[];
  dropped: number;
  ai_enabled: boolean;
  remaining_today: number;
  per_day: number;
}

export interface TutorReply {
  messages: TutorMessage[];
  remaining_today: number;
}

export interface TutorTranscript {
  messages: TutorMessage[];
  dropped: number;
  student_messages: number;
  hints: number;
  max_hint_level: number;
  flagged: number;
  concept_checks: Understanding[];
}

export interface RubricScore {
  criterion_id: string;
  name: string;
  score: number;
  max_points: number;
  feedback: string;
}

export interface Submission {
  id: string;
  practical_id: string;
  practical_title: string;
  course_code: string;
  lab_type: LabType;
  student_id: string;
  student_name: string;
  roll_number: string | null;
  files: Record<string, string>;
  status: "graded" | "reviewed";
  tests_passed: number;
  tests_total: number;
  test_results: TestResult[];
  rubric_score: number | null;
  max_score: number;
  rubric_breakdown: RubricScore[];
  ai_feedback: string | null;
  grading_model: string | null;
  faculty_score: number | null;
  faculty_comment: string | null;
  final_score: number | null;
  submitted_at: string;
  graded_at: string | null;
  reviewed_at: string | null;
  /** v1.1 — always null in student endpoints; faculty/HOD only. */
  integrity?: IntegrityReport | null;
}

export interface HealthResponse {
  status: "ok";
  storage: "memory" | "postgres" | "firestore";
  auth_provider?: "local" | "firebase";
  firebase_project?: string | null;
  execution_engine: string;
  ai: { gemini_model: string; gemma_model: string; enabled: boolean };
}

// ---------- Student ----------
export type StudentProgress = "not_started" | "in_progress" | "submitted" | "graded";

export interface StudentPracticalSummary {
  id: string;
  title: string;
  course_id: string;
  course_code: string;
  course_title: string;
  lab_type: LabType;
  due_at: string | null;
  max_score: number;
  progress: StudentProgress;
  best_score: number | null;
  attempts: number;
  last_activity_at: string | null;
  /** latest submission (null until the student submits) */
  submitted_at: string | null;
  tests_passed: number | null;
  tests_total: number | null;
  reviewed: boolean;
  /** faculty comment if reviewed, otherwise the AI rubric feedback */
  feedback: string | null;
}

export interface StudentDashboard {
  user: User;
  courses: Course[];
  practicals: StudentPracticalSummary[];
  stats: { assigned: number; completed: number; avg_score: number | null; hints_used: number };
  recent_submissions: Submission[];
}

// ---------- Faculty ----------
export interface FacultyPracticalSummary {
  id: string;
  title: string;
  course_id: string;
  course_code: string;
  lab_type: LabType;
  status: PracticalStatus;
  due_at: string | null;
  max_score: number;
  enrolled: number;
  submitted: number;
  avg_score: number | null;
  pass_rate: number | null;
  /** v1.2 */
  proctored?: boolean;
  lockdown_mode?: LockdownMode;
}

export interface FacultyDashboard {
  courses: Course[];
  practicals: FacultyPracticalSummary[];
  recent_submissions: Submission[];
  stats: {
    courses: number;
    practicals: number;
    submissions: number;
    pending_review: number;
    avg_score: number | null;
  };
}

export interface PracticalTemplate {
  description: string;
  starter_files: Record<string, string>;
  test_cases: TestCaseSpec[];
  rubric: RubricCriterion[];
}

export interface PracticalInput {
  course_id: string;
  title: string;
  description: string;
  lab_type: LabType;
  starter_files: Record<string, string>;
  test_cases: TestCaseSpec[];
  rubric: RubricCriterion[];
  max_score: number;
  due_at: string | null;
  status: PracticalStatus;
  proctored: boolean;
  /** v1.2 — a lockdown mode forces proctored = true on the server */
  lockdown_mode: LockdownMode;
  /** 64-hex SEB Config Key, required for "seb" */
  seb_config_key?: string | null;
  /** https://…/exam.seb (or sebs://) */
  seb_config_url?: string | null;
}

export interface GenerateTestsResponse {
  test_cases: TestCaseSpec[];
  model: string;
  source: "gemini" | "fallback";
}

// ---------- HOD ----------
export interface HodCourseRow {
  id: string;
  code: string;
  title: string;
  semester: number;
  faculty_id: string | null;
  faculty_name: string | null;
  enrolled: number;
  practicals: number;
  submissions: number;
  completion_rate: number;
  avg_score_pct: number | null;
}

export interface Bottleneck {
  practical_id: string;
  practical_title: string;
  course_code: string;
  test_name: string;
  fail_count: number;
  attempts: number;
  fail_rate: number;
  hint_requests: number;
}

export interface AtRiskStudent {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  completion_rate: number;
  avg_score_pct: number | null;
}

export interface HodOverview {
  department: { id: string; name: string; code: string; institution_name: string };
  kpis: {
    students: number;
    faculty: number;
    courses: number;
    practicals: number;
    submissions: number;
    completion_rate: number;
    avg_score_pct: number | null;
    at_risk_students: number;
    ai_hints_served: number;
    /** v1.1 — submissions with integrity risk medium or high. */
    integrity_flags?: number;
  };
  courses: HodCourseRow[];
  bottlenecks: Bottleneck[];
  at_risk: AtRiskStudent[];
  activity: { date: string; executions: number; submissions: number; hints: number }[];
  score_distribution: { bucket: string; count: number }[];
}

export interface FacultyMember {
  id: string;
  full_name: string;
  email: string;
  courses: string[];
}

export interface ComplianceRow {
  course_code: string;
  course_title: string;
  faculty_name: string | null;
  practical_title: string;
  due_at: string | null;
  enrolled: number;
  submitted: number;
  completion_rate: number;
  avg_score_pct: number | null;
  status: "compliant" | "at_risk" | "non_compliant";
}

export interface ComplianceReport {
  generated_at: string;
  department: string;
  rows: ComplianceRow[];
}

export interface AskResponse {
  answer: string;
  highlights: string[];
  table: { columns: string[]; rows: (string | number)[][] } | null;
  model: string;
  source: "gemini" | "fallback";
}

// ---------- v1.1 Proctoring & Academic Integrity ----------
export type ProctorEventType =
  | "session_start"
  | "paste_blocked"
  | "copy_blocked"
  | "cut_blocked"
  | "drop_blocked"
  | "context_menu_blocked"
  | "devtools_blocked"
  | "focus_lost"
  | "fullscreen_exit"
  | "large_insertion"
  | "break_start"
  | "break_end";

export interface ProctorEventIn {
  type: ProctorEventType;
  at: string;
  detail?: Record<string, string | number | boolean>;
}

export interface TypingStats {
  typed_chars: number;
  keystrokes: number;
  active_ms: number;
  large_insertions: number;
  large_insertion_chars: number;
  max_burst_cps: number;
}

export interface ProctorSummary {
  sessions: number;
  paste_blocked: number;
  copy_blocked: number;
  focus_lost: number;
  time_away_ms: number;
  fullscreen_exits: number;
  devtools_blocked: number;
  large_insertions: number;
  /** declared breaks (Pause button); missing on an older backend */
  breaks?: number;
  break_ms?: number;
}

export interface ProctorEventsRequest {
  session_id: string;
  events: ProctorEventIn[];
  stats?: TypingStats | null;
}

export interface ProctorEventsResponse {
  accepted: number;
  summary: ProctorSummary;
}

export type IntegritySeverity = "info" | "warning" | "critical";
export type RiskLevel = "low" | "medium" | "high";

export interface IntegritySignal {
  key: string;
  label: string;
  detail: string;
  severity: IntegritySeverity;
  weight: number;
}

export interface IntegrityReport {
  risk_level: RiskLevel;
  risk_score: number;
  ai_likelihood: number;
  summary: string;
  signals: IntegritySignal[];
  proctoring: {
    proctored: boolean;
    sessions: number;
    paste_blocked: number;
    copy_blocked: number;
    focus_lost: number;
    time_away_ms: number;
    fullscreen_exits: number;
    devtools_blocked: number;
    large_insertions: number;
    typed_chars: number;
    new_code_chars: number;
    typed_ratio: number | null;
    max_burst_cps: number;
  };
  content: { ai_style_score: number; indicators: string[]; model: string; source: "gemini" | "fallback" };
  similarity: { max_peer_similarity: number; peer_submission_id: string | null; peer_student_name: string | null };
  analyzed_at: string;
}

export interface ProctorEventOut {
  id: string;
  session_id: string;
  type: ProctorEventType | "typing_stats";
  detail: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

// ---------- v1.2 Exam Lockdown & Live Lab Monitor ----------
/** off: proctoring only · exam: strict web exam mode · seb: exam mode inside Safe Exam Browser */
export type LockdownMode = "off" | "exam" | "seb";
export type ExamStatus = "not_started" | "active" | "paused" | "locked" | "submitted";
export type ExamViolationType = "focus_lost" | "fullscreen_exit" | "devtools_blocked" | "second_tab" | "page_closed";

export interface ExamState {
  lockdown_mode: LockdownMode;
  status: ExamStatus;
  lock_reason: string | null;
  violations: number;
  locked_at: string | null;
  /** this tab (session_id) holds the exam */
  is_current_session: boolean;
  /** a mentor unlocked: call /exam/start again with this tab's session_id */
  awaiting_resume: boolean;
  seb_required: boolean;
  seb_verified: boolean;
  /** Pause button (missing on an older backend): on a declared break since */
  paused_at?: string | null;
  breaks_used?: number;
  max_breaks?: number;
  /** a break longer than this locks the exam */
  break_limit_s?: number;
}

export interface MonitorRow {
  student_id: string;
  student_name: string;
  roll_number: string | null;
  status: ExamStatus;
  online: boolean;
  last_seen_at: string | null;
  lock_reason: string | null;
  locked_at: string | null;
  violations: number;
  unlock_count: number;
  paste_blocked: number;
  copy_blocked: number;
  focus_lost: number;
  fullscreen_exits: number;
  time_away_ms: number;
  tests_passed: number | null;
  tests_total: number | null;
  submission_id: string | null;
  final_score: number | null;
  max_score: number;
  integrity_risk: RiskLevel | null;
  paused_at?: string | null;
  breaks_used?: number;
  break_ms?: number;
}

export interface MonitorResponse {
  practical_id: string;
  practical_title: string;
  course_code: string;
  lockdown_mode: LockdownMode;
  proctored: boolean;
  generated_at: string;
  counts: { not_started: number; active: number; paused?: number; locked: number; submitted: number; online: number };
  /** locked first, then active (online first), not started, submitted */
  rows: MonitorRow[];
}

export interface LockAlert {
  practical_id: string;
  practical_title: string;
  course_code: string;
  student_id: string;
  student_name: string;
  roll_number: string | null;
  lock_reason: string | null;
  locked_at: string | null;
}

export interface AlertsResponse {
  locked_count: number;
  locked: LockAlert[];
}

// ---------- AI teaching assistant & department intelligence (v1.6) ----------
export type Difficulty = "beginner" | "intermediate" | "advanced";

export interface PracticalVerification {
  verified: boolean;
  tests_total: number;
  reference_passed: number;
  starter_failed: number;
  dropped: string[];
  attempts: number;
  note: string | null;
}

export interface GeneratedPractical {
  title: string;
  description: string;
  starter_files: Record<string, string>;
  test_cases: TestCaseSpec[];
  rubric: RubricCriterion[];
  max_score: number;
  viva_questions: string[];
  /** faculty only: for Validate; never stored with the practical */
  reference_files: Record<string, string>;
  verification: PracticalVerification;
  model: string;
  source: "gemini";
}

export interface MaterialSection {
  heading: string;
  content: string;
}

export interface TeachingMaterial {
  title: string;
  overview: string;
  learning_outcomes: string[];
  sections: MaterialSection[];
  examples: MaterialSection[];
  real_world_examples: string[];
  common_mistakes: string[];
  discussion_questions: string[];
  viva_questions: { question: string; answer: string }[];
  markdown: string;
  model: string;
  source: "gemini";
}

export interface LearningDifficulty {
  concept: string;
  explanation: string;
  recommended_action: string;
  practical_id: string;
  practical_title: string;
  tests: string[];
  students_affected: number;
  students_attempted: number;
  fail_rate: number;
  hint_requests: number;
  example_questions: string[];
}

export interface LearningDifficulties {
  generated_at: string;
  courses: {
    course_id: string;
    course_code: string;
    course_title: string;
    faculty_name: string | null;
    difficulties: LearningDifficulty[];
  }[];
  model: string;
  source: "gemini" | "fallback";
  cached: boolean;
}

export interface DepartmentBriefing {
  period_start: string;
  period_end: string;
  headline: string;
  highlights: string[];
  concerns: string[];
  actions: { action: string; owner: string; reason: string }[];
  metrics: {
    period?: string;
    this_week?: Record<string, number | null>;
    last_week?: Record<string, number | null>;
    [key: string]: unknown;
  };
  markdown: string;
  generated_at: string;
  model: string;
  source: "gemini" | "fallback";
}
