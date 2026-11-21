import type { TestResult, WorksheetAnswers, WorksheetCell } from "./types";

/** answers.json -> answers; tolerant of an empty / older file. */
export function parseAnswers(raw: string | undefined): WorksheetAnswers {
  try {
    const data = JSON.parse(raw || "{}");
    const steps = data && typeof data.steps === "object" && !Array.isArray(data.steps) ? data.steps : {};
    const rows = Array.isArray(data?.rows) ? data.rows.filter((r: unknown) => r && typeof r === "object") : [];
    return { steps, rows };
  } catch {
    return { steps: {}, rows: [] };
  }
}

export function serializeAnswers(a: WorksheetAnswers): string {
  return JSON.stringify(a);
}

/** A typed or recorded value as a number (accepts the unicode minus); null when empty or not a number. */
export function num(v: WorksheetCell | undefined): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = v.trim().replace(/[−–]/g, "-");
  if (s === "" || !/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** Least-squares line through the points (null with fewer than two distinct x values). */
export function fitLine(points: [number, number][]): { m: number; c: number } | null {
  if (points.length < 2) return null;
  const n = points.length;
  const mx = points.reduce((a, p) => a + p[0], 0) / n;
  const my = points.reduce((a, p) => a + p[1], 0) / n;
  const sxx = points.reduce((a, p) => a + (p[0] - mx) ** 2, 0);
  if (sxx === 0) return null;
  const m = points.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0) / sxx;
  return { m, c: my - m * mx };
}

/** Standard normal sample (Box–Muller) for simulated instrument noise. */
export function gauss(sigma: number): number {
  const u = 1 - Math.random();
  const v = Math.random();
  return sigma * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export type CheckStatus = { state: "pass" } | { state: "fail"; message: string } | { state: "todo"; message: string } | null;

/** The check failed only because nothing has been entered yet (see WORKSHEET_PRELUDE on the backend). */
export function isUnanswered(message: string | null | undefined): boolean {
  const m = (message ?? "").replace(/^AssertionError:\s*/, "");
  return / is empty$/.test(m) || m.startsWith("No readings recorded yet") || m.startsWith("Record at least");
}

/**
 * Status of one check from the latest run, or null when it wasn't checked or the inputs it covers changed since
 * (`fresh` = the inputs are unchanged since that run).
 */
export function checkStatus(tests: TestResult[] | undefined, name: string | null, fresh: boolean): CheckStatus {
  if (!tests || !name || !fresh) return null;
  const t = tests.find((x) => x.name === name);
  if (!t) return null;
  if (t.passed) return { state: "pass" };
  const message = (t.message ?? "Not correct yet").replace(/^AssertionError:\s*/, "");
  return isUnanswered(t.message) ? { state: "todo", message } : { state: "fail", message };
}

/** Nice axis ticks covering [0, max]. */
export function ticks(max: number, count = 5): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = 0; v <= max + step * 0.5; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

export function fmtTick(v: number): string {
  if (v === 0) return "0";
  if (Math.abs(v) >= 100) return v.toFixed(0);
  if (Math.abs(v) >= 10) return v.toFixed(Number.isInteger(v) ? 0 : 1);
  return Number.isInteger(v) ? String(v) : v.toFixed(v * 10 === Math.round(v * 10) ? 1 : 2);
}
