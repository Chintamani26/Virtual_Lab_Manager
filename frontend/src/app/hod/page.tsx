"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { PageContainer } from "@/components/AppShell";
import { AnalyticsChat } from "@/components/AnalyticsChat";
import { BriefingCard, DifficultiesCard } from "@/components/insights";
import { ActivityCharts, ScoreDistributionChart, ViewToggle } from "@/components/HodCharts";
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  InlineError,
  PageHeader,
  PageSkeleton,
  ScoreBar,
  SegmentedControl,
  StatTile,
  StatusBadge,
  UnderlineTabs,
  compactSelectCls,
  cx,
} from "@/components/ui";
import { api, fmtDate, fmtPct } from "@/lib/api";
import type { ComplianceReport, FacultyMember, HodOverview } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type HodTab = "overview" | "insights" | "courses" | "compliance" | "ask";
type ComplianceFilter = "all" | "at_risk" | "non_compliant";

const THEAD = "text-xs text-slate-500";
const TH = "whitespace-nowrap px-3 py-2.5 font-medium";

export default function HodDashboardPage() {
  const { data, error, loading, reload, setData } = useApi(() => api.hodOverview());
  const [tab, setTab] = useState<HodTab>("overview");
  const [faculty, setFaculty] = useState<FacultyMember[]>([]);
  const [compliance, setCompliance] = useState<ComplianceReport | null>(null);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [complianceFilter, setComplianceFilter] = useState<ComplianceFilter>("all");
  const [downloading, setDownloading] = useState(false);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activityAsTable, setActivityAsTable] = useState(false);

  useEffect(() => {
    api.hodFaculty().then(setFaculty).catch(() => setFaculty([]));
    api
      .complianceReport()
      .then(setCompliance)
      .catch((e) => setComplianceError(e instanceof Error ? e.message : "Failed to load compliance report"));
  }, []);

  const filteredCompliance = useMemo(() => {
    if (!compliance) return [];
    if (complianceFilter === "all") return compliance.rows;
    return compliance.rows.filter((r) => r.status === complianceFilter);
  }, [compliance, complianceFilter]);

  async function assign(courseId: string, facultyId: string) {
    if (!data || !facultyId) return;
    setAssigning(courseId);
    setActionError(null);
    try {
      const course = await api.assignFaculty(courseId, facultyId);
      const next: HodOverview = {
        ...data,
        courses: data.courses.map((c) =>
          c.id === courseId ? { ...c, faculty_id: course.faculty_id, faculty_name: course.faculty_name } : c,
        ),
      };
      setData(next);
      api.hodFaculty().then(setFaculty).catch(() => undefined);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Assignment failed");
    } finally {
      setAssigning(null);
    }
  }

  async function downloadCsv() {
    setDownloading(true);
    setActionError(null);
    try {
      const res = await api.complianceCsv();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `compliance-report-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  if (loading && !data)
    return (
      <PageContainer>
        <PageSkeleton tiles={4} />
      </PageContainer>
    );
  if (error || !data)
    return (
      <PageContainer>
        <ErrorState message={error ?? "No data"} onRetry={reload} />
      </PageContainer>
    );

  const { kpis, department } = data;
  const tabs: { key: HodTab; label: string; count?: number }[] = [
    { key: "overview", label: "Overview" },
    { key: "insights", label: "AI insights" },
    { key: "courses", label: "Courses", count: data.courses.length },
    { key: "compliance", label: "Compliance", count: compliance?.rows.length },
    { key: "ask", label: "Ask" },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={department.name}
        subtitle={`${department.code} · ${department.institution_name} · ${kpis.students} students · ${kpis.faculty} faculty`}
        actions={
          <Button variant="secondary" size="sm" loading={downloading} onClick={downloadCsv}>
            Export CSV
          </Button>
        }
      />

      {actionError && (
        <div className="mb-4">
          <InlineError message={actionError} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Completion" value={fmtPct(kpis.completion_rate)} hint={`${kpis.submissions} submissions`} />
        <StatTile label="Average score" value={fmtPct(kpis.avg_score_pct)} hint={`${kpis.courses} courses`} />
        <StatTile label="At-risk students" value={kpis.at_risk_students} />
        <StatTile label="Integrity flags" value={kpis.integrity_flags ?? 0} />
      </div>

      <UnderlineTabs
        label="Department sections"
        tabs={tabs}
        active={tab}
        onChange={setTab}
        className="mt-8"
      />

      {tab === "overview" && (
        <div className="mt-6 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
            <Card>
              <CardHeader
                title="Lab activity"
                subtitle="Last 14 days"
                action={data.activity.length > 0 && <ViewToggle asTable={activityAsTable} onChange={setActivityAsTable} />}
              />
              <div className="p-5">
                {data.activity.length === 0 ? (
                  <EmptyState title="No activity yet." />
                ) : (
                  <ActivityCharts data={data.activity} asTable={activityAsTable} />
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Score distribution" subtitle="Graded submissions" />
              <div className="p-5">
                {data.score_distribution.every((b) => b.count === 0) ? (
                  <EmptyState title="No graded submissions yet." />
                ) : (
                  <ScoreDistributionChart data={data.score_distribution} />
                )}
              </div>
            </Card>
          </div>

          <div className="grid items-start gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="At-risk students" subtitle="Low completion or score" />
              {data.at_risk.length === 0 ? (
                <EmptyState title="No at-risk students." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className={THEAD}>
                      <tr className="border-b border-slate-100">
                        <th className={cx(TH, "pl-5")}>Student</th>
                        <th className={cx(TH, "text-right")}>Completion</th>
                        <th className={cx(TH, "pr-5 text-right")}>Avg score</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.at_risk.map((s) => (
                        <tr key={s.student_id} className="hover:bg-slate-50/60">
                          <td className="w-full max-w-0 py-3 pl-5 pr-3">
                            <p className="truncate font-medium text-slate-900">{s.student_name}</p>
                            <p className="font-mono text-xs text-slate-500">{s.roll_number ?? "—"}</p>
                          </td>
                          <td className="px-3 py-3 text-right tabular-nums text-slate-700">{fmtPct(s.completion_rate)}</td>
                          <td className="py-3 pl-3 pr-5 text-right tabular-nums text-slate-900">{fmtPct(s.avg_score_pct)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Bottlenecks" subtitle="Tests failed most often" />
              {data.bottlenecks.length === 0 ? (
                <EmptyState title="No failing tests yet." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className={THEAD}>
                      <tr className="border-b border-slate-100">
                        <th className={cx(TH, "pl-5")}>Test</th>
                        <th className={TH}>Fail rate</th>
                        <th className={cx(TH, "pr-5 text-right")}>Hints</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.bottlenecks.map((b) => (
                        <tr key={`${b.practical_id}-${b.test_name}`} className="hover:bg-slate-50/60">
                          <td className="py-3 pl-5 pr-3">
                            <p className="font-mono text-xs font-medium text-slate-900">{b.test_name}</p>
                            <p className="mt-0.5 text-xs text-slate-500">
                              {b.course_code} · {b.practical_title}
                            </p>
                          </td>
                          <td className="px-3 py-3">
                            <div className="flex w-28 items-center gap-2">
                              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                                <div className="h-full rounded-full bg-rose-500" style={{ width: `${Math.min(100, b.fail_rate)}%` }} />
                              </div>
                              <span className="w-8 text-right text-xs tabular-nums text-slate-700">
                                {Math.round(b.fail_rate)}%
                              </span>
                            </div>
                            <p className="mt-0.5 text-xs tabular-nums text-slate-400">
                              {b.fail_count}/{b.attempts} runs
                            </p>
                          </td>
                          <td className="py-3 pl-3 pr-5 text-right tabular-nums text-slate-700">{b.hint_requests}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}

      {tab === "courses" && (
        <Card className="mt-6">
          <CardHeader title="Courses and faculty" subtitle="Assign faculty and monitor course progress" />
          {data.courses.length === 0 ? (
            <EmptyState title="No courses in this department." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className={THEAD}>
                  <tr className="border-b border-slate-100">
                    <th className={cx(TH, "pl-5")}>Course</th>
                    <th className={TH}>Faculty</th>
                    <th className={cx(TH, "text-right")}>Students</th>
                    <th className={cx(TH, "text-right")}>Labs</th>
                    <th className={TH}>Completion</th>
                    <th className={cx(TH, "pr-5 text-right")}>Avg score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.courses.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50/60">
                      <td className="py-3 pl-5 pr-3">
                        <p className="font-medium text-slate-900">{c.title}</p>
                        <p className="mt-0.5 text-xs text-slate-500">
                          <span className="font-mono">{c.code}</span> · Semester {c.semester}
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2">
                          <select
                            aria-label={`Faculty for ${c.code}`}
                            value={c.faculty_id ?? ""}
                            onChange={(e) => assign(c.id, e.target.value)}
                            disabled={assigning === c.id || faculty.length === 0}
                            className={cx(
                              compactSelectCls,
                              "h-8 w-44 text-sm",
                              !c.faculty_id && "border-amber-300 text-amber-800",
                            )}
                          >
                            {!c.faculty_id && <option value="">Unassigned</option>}
                            {faculty.length === 0 && c.faculty_id && <option value={c.faculty_id}>{c.faculty_name}</option>}
                            {faculty.map((f) => (
                              <option key={f.id} value={f.id}>
                                {f.full_name}
                              </option>
                            ))}
                          </select>
                          {assigning === c.id && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-slate-700">{c.enrolled}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-slate-700">{c.practicals}</td>
                      <td className="px-3 py-3">
                        <div className="flex w-36 items-center gap-2">
                          <div className="flex-1">
                            <ScoreBar value={c.completion_rate} max={100} />
                          </div>
                          <span className="w-9 text-right tabular-nums text-slate-700">{fmtPct(c.completion_rate)}</span>
                        </div>
                      </td>
                      <td className="py-3 pl-3 pr-5 text-right tabular-nums text-slate-900">{fmtPct(c.avg_score_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "compliance" && (
        <Card className="mt-6">
          <CardHeader
            title="Compliance report"
            subtitle={compliance ? `Updated ${fmtDate(compliance.generated_at, true)}` : undefined}
            action={
              compliance && compliance.rows.length > 0 ? (
                <SegmentedControl
                  ariaLabel="Filter compliance rows"
                  value={complianceFilter}
                  onChange={setComplianceFilter}
                  options={[
                    { value: "all", label: "All" },
                    { value: "at_risk", label: "At risk" },
                    { value: "non_compliant", label: "Non-compliant" },
                  ]}
                />
              ) : undefined
            }
          />
          {complianceError ? (
            <div className="p-5">
              <InlineError message={complianceError} />
            </div>
          ) : !compliance ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : filteredCompliance.length === 0 ? (
            <EmptyState
              title={compliance.rows.length === 0 ? "No published practicals." : "No practicals match this filter."}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className={THEAD}>
                  <tr className="border-b border-slate-100">
                    <th className={cx(TH, "pl-5")}>Practical</th>
                    <th className={TH}>Faculty</th>
                    <th className={TH}>Due</th>
                    <th className={cx(TH, "text-right")}>Submitted</th>
                    <th className={cx(TH, "text-right")}>Avg score</th>
                    <th className={cx(TH, "pr-5")}>Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredCompliance.map((r, i) => (
                    <tr key={i} className="hover:bg-slate-50/60">
                      <td className="py-3 pl-5 pr-3">
                        <p className="font-medium text-slate-900">{r.practical_title}</p>
                        <p className="mt-0.5 font-mono text-xs text-slate-500">{r.course_code}</p>
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-slate-700">{r.faculty_name ?? "—"}</td>
                      <td className="whitespace-nowrap px-3 py-3 text-slate-700">{fmtDate(r.due_at)}</td>
                      <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums text-slate-900">
                        {r.submitted}/{r.enrolled}{" "}
                        <span className="text-xs text-slate-500">({fmtPct(r.completion_rate)})</span>
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-slate-900">{fmtPct(r.avg_score_pct)}</td>
                      <td className="py-3 pl-3 pr-5">
                        <StatusBadge status={r.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "insights" && (
        <div className="mt-6 space-y-6">
          <BriefingCard />
          <DifficultiesCard scope="hod" />
        </div>
      )}

      {tab === "ask" && (
        <div className="mt-6 max-w-3xl">
          <AnalyticsChat />
        </div>
      )}
    </PageContainer>
  );
}
