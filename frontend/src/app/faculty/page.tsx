"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { PageContainer } from "@/components/AppShell";
import { DifficultiesCard } from "@/components/insights";
import { IntegrityBadge } from "@/components/integrity";
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  InlineError,
  LinkButton,
  PageHeader,
  PageSkeleton,
  SegmentedControl,
  StatTile,
  StatusBadge,
  UnderlineTabs,
  compactSelectCls,
  cx,
} from "@/components/ui";
import { api, fmtDate, fmtPct, fmtScore, relativeDue } from "@/lib/api";
import type { LabType, LockdownMode } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LAB_LABEL: Record<LabType, string> = {
  coding: "Coding",
  circuit: "Circuit",
  notebook: "Notebook",
  worksheet: "Worksheet",
};
const LOCKDOWN_LABEL: Partial<Record<LockdownMode, string>> = { exam: "Exam mode", seb: "SEB exam" };

const th = "px-3 py-2.5 font-medium";
const primaryLink = "font-medium text-indigo-600 hover:text-indigo-500";
const secondaryLink = "text-slate-600 hover:text-slate-900";

type DashboardTab = "practicals" | "submissions" | "courses" | "insights";

function DueText({ dueAt }: { dueAt: string | null }) {
  const d = relativeDue(dueAt);
  return (
    <span
      className={cx(
        "whitespace-nowrap",
        d.tone === "late" ? "text-rose-700" : d.tone === "soon" ? "text-amber-700" : "text-slate-700",
      )}
    >
      {d.label}
    </span>
  );
}

export default function FacultyDashboardPage() {
  const { data, error, loading, reload } = useApi(() => api.facultyDashboard());
  const [tab, setTab] = useState<DashboardTab>("practicals");
  const [courseFilter, setCourseFilter] = useState<string>("all");
  const [onlyPending, setOnlyPending] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const filteredPracticals = useMemo(() => {
    if (!data) return [];
    if (courseFilter === "all") return data.practicals;
    return data.practicals.filter((p) => p.course_id === courseFilter);
  }, [data, courseFilter]);

  const filteredSubmissions = useMemo(() => {
    if (!data) return [];
    if (!onlyPending) return data.recent_submissions;
    return data.recent_submissions.filter((s) => s.status !== "reviewed");
  }, [data, onlyPending]);

  async function publish(id: string) {
    setPublishing(id);
    setActionError(null);
    try {
      await api.publishPractical(id);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(null);
    }
  }

  if (loading && !data)
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  if (error || !data)
    return (
      <PageContainer>
        <ErrorState message={error ?? "No data"} onRetry={reload} />
      </PageContainer>
    );

  const { stats } = data;
  const tabs: { key: DashboardTab; label: string; count?: number }[] = [
    { key: "practicals", label: "Practicals", count: data.practicals.length },
    { key: "submissions", label: "Submissions", count: data.recent_submissions.length },
    { key: "insights", label: "Where students struggle" },
    ...(data.courses.length > 0 ? [{ key: "courses" as const, label: "Courses", count: data.courses.length }] : []),
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Faculty dashboard"
        actions={
          <LinkButton href="/faculty/teaching" size="sm" variant="secondary">
            Teaching material
          </LinkButton>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Practicals" value={stats.practicals} />
        <StatTile label="Submissions" value={stats.submissions} />
        <StatTile label="Pending review" value={stats.pending_review} />
        <StatTile label="Average score" value={stats.avg_score === null ? "—" : fmtScore(stats.avg_score)} />
      </div>

      <UnderlineTabs
        label="Dashboard sections"
        tabs={tabs}
        active={tab}
        onChange={setTab}
        className="mt-8"
      />

      {tab === "practicals" && (
        <Card className="mt-6">
          <CardHeader
            title="Practicals"
            action={
              data.courses.length > 1 ? (
                <select
                  aria-label="Filter by course"
                  value={courseFilter}
                  onChange={(e) => setCourseFilter(e.target.value)}
                  className={compactSelectCls}
                >
                  <option value="all">All courses</option>
                  {data.courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} · {c.title}
                    </option>
                  ))}
                </select>
              ) : undefined
            }
          />
          {actionError && (
            <div className="px-5 pt-4">
              <InlineError message={actionError} />
            </div>
          )}
          {filteredPracticals.length === 0 ? (
            <EmptyState
              title={courseFilter === "all" ? "No practicals yet." : "No practicals in this course."}
              action={
                courseFilter === "all" ? (
                  <LinkButton href="/faculty/practicals/new" size="sm">
                    New practical
                  </LinkButton>
                ) : (
                  <Button size="sm" variant="secondary" onClick={() => setCourseFilter("all")}>
                    Show all courses
                  </Button>
                )
              }
            />
          ) : (
            <div className="relative overflow-x-auto">
              <table className="w-full min-w-[740px] text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr className="border-b border-slate-100">
                    <th className={cx(th, "min-w-56 pl-5")}>Practical</th>
                    <th className={th}>Status</th>
                    <th className={th}>Due</th>
                    <th className={th}>Submitted</th>
                    <th className={th}>Avg score</th>
                    <th className={cx(th, "pr-5")}>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredPracticals.map((p) => {
                    const lockdown = p.lockdown_mode ? LOCKDOWN_LABEL[p.lockdown_mode] : undefined;
                    return (
                      <tr key={p.id} className="hover:bg-slate-50/60">
                        <td className="py-3 pl-5 pr-3">
                          <Link
                            href={`/faculty/practicals/${p.id}/submissions`}
                            className="font-medium text-slate-900 hover:text-indigo-600"
                          >
                            {p.title}
                          </Link>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {p.course_code} · {LAB_LABEL[p.lab_type]}
                            {lockdown && <> · {lockdown}</>}
                          </p>
                        </td>
                        <td className="px-3 py-3">
                          <StatusBadge status={p.status} />
                        </td>
                        <td className="px-3 py-3">
                          <DueText dueAt={p.due_at} />
                        </td>
                        <td className="px-3 py-3 tabular-nums text-slate-700">
                          {p.submitted}/{p.enrolled}
                        </td>
                        <td className="px-3 py-3 tabular-nums">
                          <p className="text-slate-900">{fmtScore(p.avg_score, p.max_score)}</p>
                          {p.pass_rate !== null && (
                            <p className="mt-0.5 text-xs text-slate-500">{fmtPct(p.pass_rate)} pass</p>
                          )}
                        </td>
                        <td className="py-3 pl-3 pr-5">
                          <div className="flex items-center justify-end gap-4 whitespace-nowrap text-sm">
                            {p.status === "draft" && (
                              <Button size="sm" loading={publishing === p.id} onClick={() => publish(p.id)}>
                                Publish
                              </Button>
                            )}
                            <Link href={`/faculty/practicals/${p.id}/submissions`} className={primaryLink}>
                              Submissions
                            </Link>
                            {p.status === "published" && (
                              <Link href={`/faculty/practicals/${p.id}/monitor`} className={secondaryLink}>
                                Monitor
                              </Link>
                            )}
                            <Link href={`/faculty/practicals/${p.id}/edit`} className={secondaryLink}>
                              Edit
                            </Link>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "submissions" && (
        <Card className="mt-6">
          <CardHeader
            title="Recent submissions"
            action={
              data.recent_submissions.length > 0 ? (
                <SegmentedControl
                  ariaLabel="Filter submissions"
                  value={onlyPending ? "pending" : "all"}
                  onChange={(v) => setOnlyPending(v === "pending")}
                  options={[
                    { value: "all", label: "All" },
                    { value: "pending", label: "Pending review" },
                  ]}
                />
              ) : undefined
            }
          />
          {filteredSubmissions.length === 0 ? (
            <EmptyState title={onlyPending ? "All recent submissions are reviewed." : "No submissions yet."} />
          ) : (
            <div className="relative overflow-x-auto">
              <table className="w-full min-w-[740px] text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr className="border-b border-slate-100">
                    <th className={cx(th, "min-w-40 pl-5")}>Student</th>
                    <th className={cx(th, "min-w-48")}>Practical</th>
                    <th className={th}>Score</th>
                    <th className={th}>Integrity</th>
                    <th className={th}>Status</th>
                    <th className={cx(th, "pr-5")}>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredSubmissions.map((s) => (
                    <tr key={s.id} className="hover:bg-slate-50/60">
                      <td className="py-3 pl-5 pr-3">
                        <p className="font-medium text-slate-900">{s.student_name}</p>
                        <p className="font-mono text-xs text-slate-500">{s.roll_number ?? "—"}</p>
                      </td>
                      <td className="px-3 py-3">
                        <p className="text-slate-900">{s.practical_title}</p>
                        <p className="mt-0.5 text-xs text-slate-500">{s.course_code}</p>
                      </td>
                      <td className="px-3 py-3 tabular-nums">
                        <p className="font-medium text-slate-900">
                          {fmtScore(s.final_score ?? s.rubric_score, s.max_score)}
                        </p>
                        <p className="mt-0.5 text-xs text-slate-500">
                          {s.tests_passed}/{s.tests_total} tests
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        <IntegrityBadge integrity={s.integrity ?? null} />
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge status={s.status} />
                        <p className="mt-1 whitespace-nowrap text-xs text-slate-500">{fmtDate(s.submitted_at, true)}</p>
                      </td>
                      <td className="py-3 pl-3 pr-5 text-right">
                        <Link href={`/faculty/submissions/${s.id}`} className={primaryLink}>
                          Review
                        </Link>
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
        <div className="mt-6">
          <DifficultiesCard scope="faculty" />
        </div>
      )}

      {tab === "courses" && (
        <Card className="mt-6">
          <CardHeader title="Courses" />
          <ul className="divide-y divide-slate-100 text-sm">
            {data.courses.map((c) => {
              const count = data.practicals.filter((p) => p.course_id === c.id).length;
              return (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-3.5">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{c.title}</p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      <span className="font-mono">{c.code}</span> · Semester {c.semester} · {c.enrolled} students ·{" "}
                      {count} {count === 1 ? "practical" : "practicals"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setCourseFilter(c.id);
                      setTab("practicals");
                    }}
                    className={primaryLink}
                  >
                    View practicals
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </PageContainer>
  );
}
