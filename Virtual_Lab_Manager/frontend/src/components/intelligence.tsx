"use client";

/**
 * Student & Faculty Intelligence UI components.
 * All five intelligence features for Faculty and HOD scopes.
 * Uses existing UI primitives from ui.tsx — no decorative icons.
 */

import { useState } from "react";
import { api, fmtDate, fmtPct } from "@/lib/api";
import type {
  AtRiskStudentExtended,
  CompletionRow,
  DifficultyHeatmapRow,
  FacultyWorkloadReport,
  HodFacultyWorkloadRow,
  IntelAtRiskReport,
  IntelHeatmapReport,
  IntelPerformanceReport,
  HodFacultyWorkloadReport,
  PerformancePractical,
  RubricBreakdownItem,
} from "@/lib/types";
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  ScoreBar,
  SegmentedControl,
  StatTile,
  cx,
} from "@/components/ui";
import { useApi } from "@/lib/useApi";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TH = "whitespace-nowrap px-3 py-2.5 font-medium text-xs text-slate-500";
const TD = "px-3 py-3 text-sm";

function RiskBadge({ level }: { level: "high" | "medium" | "low" }) {
  const cls =
    level === "high"
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : level === "medium"
        ? "bg-amber-50 text-amber-700 ring-amber-200"
        : "bg-emerald-50 text-emerald-700 ring-emerald-200";
  return (
    <span className={cx("inline-flex rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset capitalize", cls)}>
      {level}
    </span>
  );
}

function MiniBar({ value, max = 100, color = "bg-indigo-500" }: { value: number; max?: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="flex w-24 items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={cx("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-slate-700">{Math.round(value)}%</span>
    </div>
  );
}

function FailBar({ rate }: { rate: number }) {
  return (
    <div className="flex w-28 items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-rose-500" style={{ width: `${Math.min(100, rate)}%` }} />
      </div>
      <span className="w-9 text-right text-xs tabular-nums text-slate-700">{Math.round(rate)}%</span>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3 p-5">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-4 rounded bg-slate-100" style={{ width: `${60 + i * 10}%` }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1. Performance Card
// ---------------------------------------------------------------------------

function PracticalPerformanceRow({ p }: { p: PerformancePractical }) {
  const [open, setOpen] = useState(false);
  const hasRubric = p.rubric_breakdown.length > 0;

  return (
    <>
      <tr
        className={cx("hover:bg-slate-50/60", open && "bg-slate-50/60")}
        onClick={() => setOpen((v) => !v)}
        style={{ cursor: "pointer" }}
      >
        <td className="py-3 pl-5 pr-3">
          <p className="font-medium text-slate-900">{p.practical_title}</p>
          <p className="mt-0.5 text-xs text-slate-500">{p.course_code}</p>
        </td>
        <td className={TD}>
          <span className="tabular-nums text-slate-900">{p.submitted}/{p.enrolled}</span>
        </td>
        <td className={TD}>
          <MiniBar value={p.avg_score_pct ?? 0} color={p.avg_score_pct !== null && p.avg_score_pct >= 50 ? "bg-indigo-500" : "bg-rose-400"} />
        </td>
        <td className={TD}>
          {p.pass_rate !== null ? (
            <span className={cx("tabular-nums", p.pass_rate < 50 ? "text-rose-700" : "text-slate-700")}>
              {fmtPct(p.pass_rate)}
            </span>
          ) : (
            <span className="text-slate-400">—</span>
          )}
        </td>
        <td className={cx(TD, "text-slate-700 tabular-nums")}>{p.hint_usage.total}</td>
        <td className="py-3 pl-3 pr-5 text-right">
          <button type="button" className="text-xs text-indigo-600 hover:text-indigo-500">
            {open ? "Collapse" : "Details"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} className="bg-slate-50/80 px-5 pb-4 pt-2">
            <div className="grid gap-4 lg:grid-cols-2">
              {/* Score distribution */}
              <div>
                <p className="mb-2 text-xs font-medium text-slate-600">Score distribution</p>
                <div className="space-y-1">
                  {p.score_distribution.map((b) => (
                    <div key={b.bucket} className="flex items-center gap-2 text-xs">
                      <span className="w-14 text-right tabular-nums text-slate-500">{b.bucket}%</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
                        <div
                          className="h-full rounded-full bg-indigo-400"
                          style={{ width: `${Math.min(100, (b.count / Math.max(1, p.submitted)) * 100)}%` }}
                        />
                      </div>
                      <span className="w-6 text-right tabular-nums text-slate-700">{b.count}</span>
                    </div>
                  ))}
                </div>
              </div>
              {/* Rubric breakdown */}
              {hasRubric && (
                <div>
                  <p className="mb-2 text-xs font-medium text-slate-600">Rubric breakdown</p>
                  <div className="space-y-1">
                    {p.rubric_breakdown.map((r) => (
                      <div key={r.criterion_id} className="flex items-center gap-2 text-xs">
                        <span className="min-w-0 flex-1 truncate text-slate-700">{r.criterion_name}</span>
                        <MiniBar value={r.avg_pct} color={r.avg_pct >= 60 ? "bg-indigo-400" : "bg-amber-400"} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function PerformanceCard({ scope, courseId }: { scope: "faculty" | "hod"; courseId?: string }) {
  const { data, error, loading } = useApi(
    () => (scope === "faculty" ? api.facultyPerformance(courseId) : api.hodPerformance()),
    [scope, courseId],
  );

  const allPracticals = data?.courses.flatMap((c) => c.practicals) ?? [];

  return (
    <Card>
      <CardHeader
        title="Student Performance"
        subtitle={
          scope === "hod" ? "Department-wide score distributions and rubric breakdowns" : "Score distributions and rubric breakdowns per lab"
        }
      />
      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} />
        </div>
      ) : allPracticals.length === 0 ? (
        <EmptyState title="No published practicals with submissions yet." />
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[600px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className={cx(TH, "pl-5")}>Practical</th>
                <th className={TH}>Submitted</th>
                <th className={TH}>Avg score</th>
                <th className={TH}>Pass rate</th>
                <th className={TH}>Hints</th>
                <th className={cx(TH, "pr-5")}></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {allPracticals.map((p) => (
                <PracticalPerformanceRow key={p.practical_id} p={p} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 2. Workload Card (Faculty) + Faculty Workload Table (HOD)
// ---------------------------------------------------------------------------

export function WorkloadCard({ scope }: { scope: "faculty" | "hod" }) {
  if (scope === "hod") return <HodWorkloadCard />;
  return <FacultyWorkloadCard />;
}

function FacultyWorkloadCard() {
  const { data, error, loading } = useApi(() => api.facultyWorkload());

  return (
    <Card>
      <CardHeader title="My Workload" subtitle="Grading queue and turnaround" />
      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} />
        </div>
      ) : !data ? null : (
        <>
          <div className="grid grid-cols-2 gap-4 px-5 pb-4 pt-2 lg:grid-cols-4">
            <StatTile label="Pending review" value={data.pending_review} hint="Needs instructor grade" />
            <StatTile
              label="Oldest pending"
              value={data.oldest_pending_days !== null ? `${data.oldest_pending_days}d` : "—"}
              hint="Days since submitted"
            />
            <StatTile label="Reviewed (7d)" value={data.reviewed_this_week} hint="Reviewed this week" />
            <StatTile
              label="Avg turnaround"
              value={data.avg_turnaround_days !== null ? `${data.avg_turnaround_days}d` : "—"}
              hint="Days to review"
            />
          </div>
          {data.by_course.length > 0 && (
            <div className="border-t border-slate-100">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={cx(TH, "pl-5")}>Course</th>
                    <th className={cx(TH, "text-right")}>Pending</th>
                    <th className={cx(TH, "pr-5 text-right")}>Reviewed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.by_course.map((r) => (
                    <tr key={r.course_code} className="hover:bg-slate-50/60">
                      <td className="py-3 pl-5 pr-3">
                        <p className="font-medium text-slate-900">{r.course_title}</p>
                        <p className="font-mono text-xs text-slate-500">{r.course_code}</p>
                      </td>
                      <td
                        className={cx(
                          "px-3 py-3 text-right tabular-nums",
                          r.pending > 0 ? "font-semibold text-amber-700" : "text-slate-700",
                        )}
                      >
                        {r.pending}
                      </td>
                      <td className="py-3 pl-3 pr-5 text-right tabular-nums text-slate-700">{r.reviewed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function HodWorkloadCard() {
  const { data, error, loading } = useApi(() => api.hodFacultyWorkload());

  return (
    <Card>
      <CardHeader title="Faculty Workload" subtitle={`Dept avg pending: ${data?.dept_avg_pending ?? "—"}`} />
      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} />
        </div>
      ) : !data || data.faculty.length === 0 ? (
        <EmptyState title="No faculty data available." />
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className={cx(TH, "pl-5")}>Faculty</th>
                <th className={TH}>Courses</th>
                <th className={TH}>Practicals</th>
                <th className={cx(TH, "text-right")}>Pending</th>
                <th className={cx(TH, "text-right")}>Oldest (d)</th>
                <th className={cx(TH, "pr-5 text-right")}>Avg turnaround</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.faculty.map((f) => (
                <tr key={f.faculty_id} className={cx("hover:bg-slate-50/60", f.workload_flag && "bg-amber-50/60")}>
                  <td className="py-3 pl-5 pr-3">
                    <p className="font-medium text-slate-900">
                      {f.faculty_name}
                      {f.workload_flag && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                          High load
                        </span>
                      )}
                    </p>
                  </td>
                  <td className={cx(TD, "tabular-nums text-slate-700")}>{f.courses_taught}</td>
                  <td className={cx(TD, "tabular-nums text-slate-700")}>{f.practicals_count}</td>
                  <td
                    className={cx(
                      "px-3 py-3 text-right tabular-nums",
                      f.pending_review > 0 ? "font-semibold text-amber-700" : "text-slate-700",
                    )}
                  >
                    {f.pending_review}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-slate-700">
                    {f.oldest_pending_days !== null ? f.oldest_pending_days : "—"}
                  </td>
                  <td className="py-3 pl-3 pr-5 text-right tabular-nums text-slate-700">
                    {f.avg_turnaround_days !== null ? `${f.avg_turnaround_days}d` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 3. Completion Card
// ---------------------------------------------------------------------------

type CompletionFilter = "all" | "overdue" | "pacing";

export function CompletionCard({ scope }: { scope: "faculty" | "hod" }) {
  const [filter, setFilter] = useState<CompletionFilter>("all");
  const { data, error, loading } = useApi(() =>
    scope === "faculty" ? api.facultyCompletion() : api.hodCompletion(),
  );

  const rows = data ?? [];
  const filtered =
    filter === "overdue"
      ? rows.filter((r) => r.overdue > 0)
      : filter === "pacing"
        ? rows.filter((r) => r.pacing_gap)
        : rows;

  return (
    <Card>
      <CardHeader
        title="Completion Tracking"
        subtitle="Submitted vs. overdue per practical"
        action={
          rows.length > 0 ? (
            <SegmentedControl
              ariaLabel="Filter completion"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All" },
                { value: "overdue", label: "Overdue" },
                { value: "pacing", label: "Pacing gap" },
              ]}
            />
          ) : undefined
        }
      />
      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title={rows.length === 0 ? "No published practicals yet." : "No practicals match this filter."}
        />
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className={cx(TH, "pl-5")}>Practical</th>
                <th className={TH}>Due</th>
                <th className={cx(TH, "text-right")}>Submitted</th>
                <th className={cx(TH, "text-right")}>Overdue</th>
                <th className={cx(TH, "pr-5")}>Completion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((r) => (
                <tr
                  key={r.practical_id}
                  className={cx("hover:bg-slate-50/60", r.pacing_gap && "bg-amber-50/40")}
                >
                  <td className="py-3 pl-5 pr-3">
                    <p className="font-medium text-slate-900">
                      {r.practical_title}
                      {r.pacing_gap && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                          Pacing gap
                        </span>
                      )}
                    </p>
                    <p className="font-mono text-xs text-slate-500">{r.course_code}</p>
                  </td>
                  <td className={cx(TD, "tabular-nums text-slate-700")}>{fmtDate(r.due_at)}</td>
                  <td className={cx(TD, "text-right tabular-nums text-slate-700")}>
                    {r.submitted}/{r.enrolled}
                  </td>
                  <td
                    className={cx(
                      "px-3 py-3 text-right tabular-nums",
                      r.overdue > 0 ? "font-semibold text-rose-700" : "text-slate-700",
                    )}
                  >
                    {r.overdue}
                  </td>
                  <td className="py-3 pl-3 pr-5">
                    <div className="flex w-32 items-center gap-2">
                      <div className="flex-1">
                        <ScoreBar
                          value={r.completion_pct}
                          max={100}
                        />
                      </div>
                      <span className="w-10 text-right text-xs tabular-nums text-slate-700">
                        {fmtPct(r.completion_pct)}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 4. At-Risk Card
// ---------------------------------------------------------------------------

type RiskFilter = "all" | "high" | "medium";

function AtRiskRow({ s }: { s: AtRiskStudentExtended }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <tr
        className="cursor-pointer hover:bg-slate-50/60"
        onClick={() => setOpen((v) => !v)}
      >
        <td className="py-3 pl-5 pr-3">
          <p className="font-medium text-slate-900">{s.student_name}</p>
          <p className="font-mono text-xs text-slate-500">{s.roll_number ?? "—"}</p>
        </td>
        <td className={TD}>
          <RiskBadge level={s.risk_level} />
          <span className="ml-2 text-xs tabular-nums text-slate-500">({s.risk_score})</span>
        </td>
        <td className={cx(TD, "tabular-nums text-slate-700")}>{fmtPct(s.completion_rate)}</td>
        <td className={cx(TD, "tabular-nums text-slate-700")}>{fmtPct(s.avg_score_pct)}</td>
        <td className={cx(TD, "text-right tabular-nums", s.overdue_count > 0 ? "text-rose-700 font-medium" : "text-slate-700")}>
          {s.overdue_count}
        </td>
        <td className="py-3 pl-3 pr-5 text-right">
          <button type="button" className="text-xs text-indigo-600 hover:text-indigo-500">
            {open ? "Hide" : "Reasons"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} className="bg-slate-50/80 px-5 pb-4 pt-2">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs font-medium text-slate-600">Risk factors</p>
                <ul className="space-y-1 text-xs text-slate-700">
                  {s.risk_reasons.map((r, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="mt-0.5 text-rose-500">•</span> {r}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-medium text-slate-600">Recommended action</p>
                <p className="text-xs text-slate-700">{s.recommended_action}</p>
                <p className="mt-2 text-xs text-slate-500">Courses: {s.courses.join(", ") || "—"}</p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function AtRiskCard({ scope }: { scope: "faculty" | "hod" }) {
  const [filter, setFilter] = useState<RiskFilter>("all");
  const { data, error, loading } = useApi(() =>
    scope === "faculty" ? api.facultyAtRisk() : api.hodAtRisk(),
  );

  const all = data?.students ?? [];
  const filtered = filter === "all" ? all : all.filter((s) => s.risk_level === filter);

  return (
    <Card>
      <CardHeader
        title="At-Risk Students"
        subtitle="Deterministic risk scores based on completion, scores, and overdue submissions"
        action={
          all.length > 0 ? (
            <SegmentedControl
              ariaLabel="Filter risk level"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All" },
                { value: "high", label: "High" },
                { value: "medium", label: "Medium" },
              ]}
            />
          ) : undefined
        }
      />
      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title={all.length === 0 ? "No at-risk students identified." : "No students match this filter."}
        />
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className={cx(TH, "pl-5")}>Student</th>
                <th className={TH}>Risk level</th>
                <th className={TH}>Completion</th>
                <th className={TH}>Avg score</th>
                <th className={cx(TH, "text-right")}>Overdue</th>
                <th className={cx(TH, "pr-5")}></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((s) => (
                <AtRiskRow key={s.student_id} s={s} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 5. Heatmap Card
// ---------------------------------------------------------------------------

export function HeatmapCard({ scope }: { scope: "faculty" | "hod" }) {
  const { data, error, loading } = useApi(() =>
    scope === "faculty" ? api.facultyHeatmap() : api.hodHeatmap(),
  );

  const rows = data?.rows ?? [];

  return (
    <Card>
      <CardHeader
        title="Learning Difficulty Heatmap"
        subtitle="Tests with the highest failure rates — sorted by severity"
      />
      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <div className="p-5">
          <ErrorState message={error} />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title="Not enough test execution data yet. Data appears once students run tests." />
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className={cx(TH, "pl-5")}>Test assertion</th>
                <th className={TH}>Fail rate</th>
                <th className={cx(TH, "text-right")}>Students failed</th>
                <th className={cx(TH, "text-right")}>Runs</th>
                <th className={cx(TH, "pr-5 text-right")}>Hints</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-slate-50/60">
                  <td className="py-3 pl-5 pr-3">
                    <p className="font-mono text-xs font-medium text-slate-900">{r.test_name}</p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {r.course_code} · {r.practical_title}
                    </p>
                  </td>
                  <td className={TD}>
                    <FailBar rate={r.fail_rate} />
                  </td>
                  <td className={cx(TD, "text-right tabular-nums text-slate-700")}>{r.students_failed}</td>
                  <td className={cx(TD, "text-right tabular-nums text-slate-700")}>{r.attempts}</td>
                  <td className="py-3 pl-3 pr-5 text-right tabular-nums text-slate-700">{r.hint_requests}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
