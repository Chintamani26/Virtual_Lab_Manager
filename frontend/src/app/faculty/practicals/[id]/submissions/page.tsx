"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { PageContainer } from "@/components/AppShell";
import { IntegrityBadge } from "@/components/integrity";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageSkeleton,
  SegmentedControl,
  StatTile,
  StatusBadge,
  cx,
} from "@/components/ui";
import { api, fmtDate, fmtScore } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { PracticalHeader } from "@/app/faculty/_components/PracticalHeader";

const th = "px-3 py-2.5 font-medium";

type Filter = "all" | "pending" | "flagged";

export default function PracticalSubmissionsPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi(
    () => Promise.all([api.getPractical(id), api.practicalSubmissions(id)]),
    [id],
  );
  const [filter, setFilter] = useState<Filter>("all");

  const filteredSubs = useMemo(() => {
    if (!data) return [];
    const subs = data[1];
    if (filter === "pending") return subs.filter((s) => s.status !== "reviewed");
    if (filter === "flagged")
      return subs.filter((s) => s.integrity && (s.integrity.risk_level === "medium" || s.integrity.risk_level === "high"));
    return subs;
  }, [data, filter]);

  if (loading && !data)
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  if (error || !data)
    return (
      <PageContainer>
        <ErrorState message={error ?? "Not found"} onRetry={reload} />
      </PageContainer>
    );

  const [practical, subs] = data;
  const scored = subs.map((s) => s.final_score ?? s.rubric_score).filter((v): v is number => v !== null);
  const avg = scored.length ? scored.reduce((a, b) => a + b, 0) / scored.length : null;
  const allPass = subs.filter((s) => s.tests_total > 0 && s.tests_passed === s.tests_total).length;
  const pending = subs.filter((s) => s.status !== "reviewed").length;

  return (
    <PageContainer>
      <PracticalHeader
        practicalId={id}
        title={practical.title}
        status={practical.status}
        subtitle={`${practical.course_code} · ${practical.course_title} · Due ${fmtDate(practical.due_at, true)}`}
        activeTab="submissions"
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Submissions" value={subs.length} />
        <StatTile label="Average score" value={avg === null ? "—" : fmtScore(Math.round(avg * 10) / 10, practical.max_score)} />
        <StatTile label="All tests passed" value={allPass} />
        <StatTile label="Pending review" value={pending} />
      </div>

      <Card className="mt-6">
        <CardHeader
          title="Submissions"
          action={
            subs.length > 0 ? (
              <SegmentedControl
                ariaLabel="Filter submissions"
                value={filter}
                onChange={setFilter}
                options={[
                  { value: "all", label: "All" },
                  { value: "pending", label: "Pending" },
                  { value: "flagged", label: "Flagged" },
                ]}
              />
            ) : undefined
          }
        />
        {filteredSubs.length === 0 ? (
          <EmptyState title={subs.length === 0 ? "No submissions yet." : "No matching submissions."} />
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr className="border-b border-slate-100">
                  <th className={cx(th, "min-w-44 pl-5")}>Student</th>
                  <th className={th}>Score</th>
                  <th className={th}>Integrity</th>
                  <th className={th}>Status</th>
                  <th className={th}>Submitted</th>
                  <th className={cx(th, "pr-5")}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredSubs.map((s) => {
                  const displayScore = s.final_score ?? s.rubric_score;
                  const overridden = s.faculty_score !== null && s.rubric_score !== null && s.faculty_score !== s.rubric_score;
                  return (
                    <tr key={s.id} className="hover:bg-slate-50/60">
                      <td className="py-3 pl-5 pr-3">
                        <p className="font-medium text-slate-900">{s.student_name}</p>
                        <p className="font-mono text-xs text-slate-500">{s.roll_number ?? "—"}</p>
                      </td>
                      <td className="px-3 py-3 tabular-nums">
                        <p className="font-medium text-slate-900">{fmtScore(displayScore, s.max_score)}</p>
                        <p className="mt-0.5 text-xs text-slate-500">
                          {s.tests_passed}/{s.tests_total} tests
                          {overridden && <> · AI {fmtScore(s.rubric_score)}</>}
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        <IntegrityBadge integrity={s.integrity ?? null} />
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge status={s.status} />
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-xs text-slate-500">{fmtDate(s.submitted_at, true)}</td>
                      <td className="py-3 pl-3 pr-5 text-right">
                        <Link href={`/faculty/submissions/${s.id}`} className="font-medium text-indigo-600 hover:text-indigo-500">
                          Review
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </PageContainer>
  );
}
