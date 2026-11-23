import type {
  AlertsResponse,
  AskResponse,
  ComplianceReport,
  Course,
  DemoAccount,
  DepartmentBriefing,
  Difficulty,
  GeneratedPractical,
  LearningDifficulties,
  TeachingMaterial,
  ExamState,
  ExamViolationType,
  ExecutionMode,
  ExecutionResult,
  FacultyDashboard,
  FacultyMember,
  GenerateTestsResponse,
  HealthResponse,
  HintResponse,
  HodOverview,
  LabType,
  LintResponse,
  LoginResponse,
  MonitorResponse,
  MonitorRow,
  Practical,
  PracticalInput,
  PracticalTemplate,
  ProctorEventOut,
  ProctorEventsRequest,
  ProctorEventsResponse,
  StudentDashboard,
  StudentPractical,
  Submission,
  TutorAction,
  TutorReply,
  TutorThread,
  TutorTranscript,
  User,
  // Intelligence types
  IntelPerformanceReport,
  FacultyWorkloadReport,
  CompletionRow,
  IntelAtRiskReport,
  IntelHeatmapReport,
  HodFacultyWorkloadReport,
} from "./types";
import { firebaseEnabled, firebaseIdToken, firebaseSignIn, firebaseSignOut, watchIdToken } from "./firebase";

export const API_URL = (
  typeof window !== "undefined"
    ? ""
    : (process.env.INTERNAL_API_URL || "http://127.0.0.1:8000")
).replace(/\/+$/, "");

const TOKEN_KEY = "vlm.token";
const USER_KEY = "vlm.user";

// ---------- session storage ----------
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: User) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  if (firebaseEnabled) void firebaseSignOut();
}

// Firebase mode: the SDK refreshes the ID token hourly; mirror it into localStorage so synchronous readers
// (route guards, keepalive requests during page unload) always see a current token.
if (typeof window !== "undefined" && firebaseEnabled) {
  watchIdToken((token) => {
    if (token && window.localStorage.getItem(USER_KEY)) window.localStorage.setItem(TOKEN_KEY, token);
  });
}

/** Bearer token for an API call: a fresh Firebase ID token in Firebase mode, else the stored API JWT. */
async function bearerToken(sync: boolean): Promise<string | null> {
  if (firebaseEnabled && !sync) return (await firebaseIdToken()) ?? getToken();
  return getToken();
}

export function homeForRole(role: User["role"]): string {
  return role === "student" ? "/student" : role === "faculty" ? "/faculty" : "/hod";
}

// ---------- exam lockdown headers (docs/API.md v1.2) ----------
// The lab workspace registers a provider while an exam-lockdown lab is open; every enforced student call
// (draft / run / lint / hint / submit, and the exam endpoints) then carries X-Exam-Session (+ SEB headers).
type HeaderProvider = () => Record<string, string>;
const examHeaderProviders = new Map<string, HeaderProvider>();

export function registerExamHeaders(practicalId: string, provider: HeaderProvider | null) {
  if (provider) examHeaderProviders.set(practicalId, provider);
  else examHeaderProviders.delete(practicalId);
}

function examHeaders(practicalId: string): Record<string, string> {
  try {
    return examHeaderProviders.get(practicalId)?.() ?? {};
  } catch {
    return {};
  }
}

// ---------- fetch wrapper ----------
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function extractDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors: [{loc, msg, type}]
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join("; ");
    }
  }
  return fallback;
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  auth?: boolean;
  raw?: boolean;
  /** keep the request alive after the page unloads (pagehide flush) */
  keepalive?: boolean;
  /** don't clear the session / redirect on 401 (background telemetry) */
  silent401?: boolean;
  headers?: Record<string, string>;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = await bearerToken(Boolean(opts.keepalive));
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      keepalive: opts.keepalive,
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is the backend running?`, 0);
  }

  if (res.status === 401 && auth && !opts.silent401) {
    clearSession();
    if (typeof window !== "undefined" && window.location.pathname !== "/") {
      window.location.href = "/";
    }
  }

  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(extractDetail(parsed, `${res.status} ${res.statusText}`), res.status);
  }

  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------- endpoints ----------
export const api = {
  health: () => request<HealthResponse>("/health", { auth: false }),

  // auth
  login: async (email: string, password: string): Promise<LoginResponse> => {
    if (!firebaseEnabled) {
      return request<LoginResponse>("/auth/login", { method: "POST", body: { email, password }, auth: false });
    }
    // Firebase mode: sign in with Firebase Auth, then ask the API who this token belongs to.
    const token = await firebaseSignIn(email, password);
    try {
      const user = await request<User>("/auth/me", { auth: false, headers: { Authorization: `Bearer ${token}` } });
      return { access_token: token, token_type: "bearer", user };
    } catch (err) {
      void firebaseSignOut(); // e.g. 403 "This sign-in has no Virtual Lab Manager account"
      throw err;
    }
  },
  me: () => request<User>("/auth/me"),
  demoAccounts: () => request<DemoAccount[]>("/auth/demo-accounts", { auth: false }),

  // student
  studentDashboard: () => request<StudentDashboard>("/student/dashboard"),
  studentPractical: (id: string) => request<StudentPractical>(`/student/practicals/${id}`),
  saveDraft: (id: string, files: Record<string, string>) =>
    request<{ saved_at: string }>(`/student/practicals/${id}/draft`, {
      method: "PUT",
      body: { files },
      headers: examHeaders(id),
    }),
  run: (id: string, files: Record<string, string>, mode: ExecutionMode) =>
    request<ExecutionResult>(`/student/practicals/${id}/run`, {
      method: "POST",
      body: { files, mode },
      headers: examHeaders(id),
    }),
  lint: (id: string, files: Record<string, string>, filename: string) =>
    request<LintResponse>(`/student/practicals/${id}/lint`, {
      method: "POST",
      body: { files, filename },
      headers: examHeaders(id),
    }),
  hint: (id: string, question?: string) =>
    request<HintResponse>(`/student/practicals/${id}/hint`, {
      method: "POST",
      body: question && question.trim() ? { question: question.trim() } : {},
      headers: examHeaders(id),
    }),
  // AI Lab Tutor (v1.5): the conversation lives on the server; only the new message / action is sent
  tutorHistory: (id: string) => request<TutorThread>(`/student/practicals/${id}/tutor`),
  tutor: (id: string, action: TutorAction, message?: string, test?: string) =>
    request<TutorReply>(`/student/practicals/${id}/tutor`, {
      method: "POST",
      body: { action, message: message?.trim() || null, test: test ?? null },
      headers: examHeaders(id),
    }),
  submit: (id: string, files: Record<string, string>) =>
    request<Submission>(`/student/practicals/${id}/submit`, {
      method: "POST",
      body: { files },
      headers: examHeaders(id),
    }),
  // exam lockdown (v1.2)
  examStart: (id: string, sessionId: string) =>
    request<ExamState>(`/student/practicals/${id}/exam/start`, {
      method: "POST",
      body: { session_id: sessionId },
      headers: examHeaders(id),
    }),
  examPause: (id: string, sessionId: string) =>
    request<ExamState>(`/student/practicals/${id}/exam/pause`, {
      method: "POST",
      body: { session_id: sessionId },
      headers: examHeaders(id),
    }),
  examResume: (id: string, sessionId: string) =>
    request<ExamState>(`/student/practicals/${id}/exam/resume`, {
      method: "POST",
      body: { session_id: sessionId },
      headers: examHeaders(id),
    }),
  examHeartbeat: (id: string, sessionId: string) =>
    request<ExamState>(`/student/practicals/${id}/exam/heartbeat`, {
      method: "POST",
      body: { session_id: sessionId },
      headers: examHeaders(id),
      silent401: true,
    }),
  examViolation: (
    id: string,
    body: { session_id: string; type: ExamViolationType; detail?: string },
    opts: { keepalive?: boolean } = {},
  ) =>
    request<ExamState>(`/student/practicals/${id}/exam/violation`, {
      method: "POST",
      body,
      headers: examHeaders(id),
      keepalive: opts.keepalive,
      silent401: true,
    }),
  studentSubmissions: () => request<Submission[]>("/student/submissions"),
  proctorEvents: (id: string, body: ProctorEventsRequest, opts: { keepalive?: boolean } = {}) =>
    request<ProctorEventsResponse>(`/student/practicals/${id}/proctor/events`, {
      method: "POST",
      body,
      keepalive: opts.keepalive,
      silent401: true,
    }),

  // faculty
  facultyDashboard: () => request<FacultyDashboard>("/faculty/dashboard"),
  template: (labType: LabType) => request<PracticalTemplate>(`/faculty/templates/${labType}`),
  createPractical: (input: PracticalInput) =>
    request<Practical>("/faculty/practicals", { method: "POST", body: input }),
  getPractical: (id: string) => request<Practical>(`/faculty/practicals/${id}`),
  updatePractical: (id: string, input: PracticalInput) =>
    request<Practical>(`/faculty/practicals/${id}`, { method: "PUT", body: input }),
  publishPractical: (id: string) => request<Practical>(`/faculty/practicals/${id}/publish`, { method: "POST" }),
  validatePractical: (id: string, files: Record<string, string>) =>
    request<ExecutionResult>(`/faculty/practicals/${id}/validate`, { method: "POST", body: { files } }),
  practicalSubmissions: (id: string) => request<Submission[]>(`/faculty/practicals/${id}/submissions`),
  getSubmission: (id: string) => request<Submission>(`/faculty/submissions/${id}`),
  submissionProctorEvents: (id: string) => request<ProctorEventOut[]>(`/faculty/submissions/${id}/proctor-events`),
  submissionTutor: (id: string) => request<TutorTranscript>(`/faculty/submissions/${id}/tutor`),
  reviewSubmission: (id: string, body: { faculty_score?: number | null; faculty_comment?: string | null }) =>
    request<Submission>(`/faculty/submissions/${id}/review`, { method: "POST", body }),
  generateTests: (body: { title: string; description: string; lab_type: LabType; reference_code?: string }) =>
    request<GenerateTestsResponse>("/faculty/ai/generate-tests", { method: "POST", body }),
  // AI teaching assistant (v1.6): drafts only, nothing is saved or published
  generatePractical: (body: { topic: string; course_id?: string; difficulty: Difficulty; duration_minutes?: number; notes?: string }) =>
    request<GeneratedPractical>("/faculty/ai/generate-practical", { method: "POST", body }),
  teachingMaterial: (body: { topic: string; course_id?: string; level: Difficulty; duration_minutes?: number; notes?: string }) =>
    request<TeachingMaterial>("/faculty/ai/teaching-material", { method: "POST", body }),
  facultyDifficulties: (refresh = false) =>
    request<LearningDifficulties>(`/faculty/ai/learning-difficulties${refresh ? "?refresh=true" : ""}`),
  hodDifficulties: (refresh = false) =>
    request<LearningDifficulties>(`/hod/ai/learning-difficulties${refresh ? "?refresh=true" : ""}`),
  hodBriefing: () => request<DepartmentBriefing>("/hod/ai/briefing", { method: "POST" }),
  // live lab monitor & exam lockdown (v1.2)
  monitor: (id: string) => request<MonitorResponse>(`/faculty/practicals/${id}/monitor`),
  unlockExam: (practicalId: string, studentId: string) =>
    request<MonitorRow>(`/faculty/practicals/${practicalId}/exam/${studentId}/unlock`, { method: "POST" }),
  lockExam: (practicalId: string, studentId: string, reason?: string) =>
    request<MonitorRow>(`/faculty/practicals/${practicalId}/exam/${studentId}/lock`, {
      method: "POST",
      body: reason && reason.trim() ? { reason: reason.trim() } : {},
    }),
  alerts: () => request<AlertsResponse>("/faculty/alerts", { silent401: true }),

  // hod
  hodOverview: () => request<HodOverview>("/hod/overview"),
  hodFaculty: () => request<FacultyMember[]>("/hod/faculty"),
  assignFaculty: (courseId: string, facultyId: string) =>
    request<Course>(`/hod/courses/${courseId}/faculty`, { method: "PUT", body: { faculty_id: facultyId } }),
  complianceReport: () => request<ComplianceReport>("/hod/compliance-report"),
  complianceCsv: () => request<Response>("/hod/compliance-report?format=csv", { raw: true }),
  ask: (question: string) => request<AskResponse>("/hod/ask", { method: "POST", body: { question } }),

  // Faculty Intelligence
  facultyPerformance: (courseId?: string) =>
    request<IntelPerformanceReport>(`/faculty/intelligence/performance${courseId ? `?course_id=${courseId}` : ""}`),
  facultyWorkload: () => request<FacultyWorkloadReport>("/faculty/intelligence/workload"),
  facultyCompletion: () => request<CompletionRow[]>("/faculty/intelligence/completion"),
  facultyAtRisk: () => request<IntelAtRiskReport>("/faculty/intelligence/at-risk"),
  facultyHeatmap: () => request<IntelHeatmapReport>("/faculty/intelligence/heatmap"),

  // HOD Intelligence
  hodPerformance: () => request<IntelPerformanceReport>("/hod/intelligence/performance"),
  hodFacultyWorkload: () => request<HodFacultyWorkloadReport>("/hod/intelligence/faculty-workload"),
  hodAtRisk: () => request<IntelAtRiskReport>("/hod/intelligence/at-risk"),
  hodHeatmap: () => request<IntelHeatmapReport>("/hod/intelligence/heatmap"),
  hodCompletion: () => request<CompletionRow[]>("/hod/intelligence/completion"),
};

// ---------- formatting helpers ----------
export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: withTime ? undefined : "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function relativeDue(iso: string | null | undefined): { label: string; tone: "ok" | "soon" | "late" | "none" } {
  if (!iso) return { label: "No deadline", tone: "none" };
  const diff = new Date(iso).getTime() - Date.now();
  const days = Math.round(diff / 86_400_000);
  if (diff < 0) return { label: `Overdue by ${Math.max(1, Math.abs(days))}d`, tone: "late" };
  if (days <= 2) return { label: days <= 0 ? "Due today" : `Due in ${days}d`, tone: "soon" };
  return { label: `Due in ${days}d`, tone: "ok" };
}

export function fmtScore(score: number | null | undefined, max?: number): string {
  if (score === null || score === undefined) return "—";
  const s = Number.isInteger(score) ? String(score) : score.toFixed(1);
  return max !== undefined ? `${s}/${max}` : s;
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${Math.round(v)}%`;
}

export const LAB_FILE: Record<LabType, string> = {
  coding: "main.py",
  circuit: "circuit.sim",
  notebook: "data.ipynb",
  worksheet: "answers.json",
};
