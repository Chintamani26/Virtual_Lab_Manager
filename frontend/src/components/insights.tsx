"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, Card, CardHeader, InlineError, Skeleton, cx } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import type { DepartmentBriefing, LearningDifficulties, LearningDifficulty } from "@/lib/types";
import { useApi } from "@/lib/useApi";

/** Save text as a file in the browser (markdown exports). */
export function downloadText(filename: string, text: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function slugify(text: string) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "document";
}

function SourceNote({ source, model, at }: { source: "gemini" | "fallback"; model: string; at?: string }) {
  return (
    <span className="text-xs text-slate-400">
      {source === "gemini" ? `Gemini · ${model}` : "Rule-based (AI unavailable)"}
      {at ? ` · ${fmtDate(at, true)}` : ""}
    </span>
  );
}

// ---------------------------------------------------------------- weekly briefing (HOD)
const METRIC_ROWS: { key: string; label: string; pct?: boolean }[] = [
  { key: "submissions", label: "Submissions" },
  { key: "active_students", label: "Active students" },
  { key: "test_runs", label: "Test runs" },
  { key: "hint_requests", label: "Hint requests" },
  { key: "avg_score_pct", label: "Average score", pct: true },
  { key: "integrity_flags", label: "Integrity flags" },
];

function fmtMetric(v: number | null | undefined, pct?: boolean) {
  if (v === null || v === undefined) return "—";
  return pct ? `${v}%` : String(v);
}

export function BriefingCard() {
  const [brief, setBrief] = useState<DepartmentBriefing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setBrief(await api.hodBriefing());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't generate the briefing");
    } finally {
      setLoading(false);
    }
  }

  const tw = brief?.metrics.this_week ?? {};
  const lw = brief?.metrics.last_week ?? {};

  return (
    <Card>
      <CardHeader
        title="Weekly briefing"
        subtitle={brief?.metrics.period ?? "A one-page summary of the last 7 days, with recommended actions"}
        action={
          <>
            {brief && (
              <Button size="sm" variant="ghost" onClick={() => downloadText(`weekly-briefing-${brief.generated_at.slice(0, 10)}.md`, brief.markdown)}>
                Download
              </Button>
            )}
            <Button size="sm" variant={brief ? "secondary" : "primary"} loading={loading} onClick={generate} data-testid="briefing-generate">
              {brief ? "Regenerate" : "Generate briefing"}
            </Button>
          </>
        }
      />
      {error && (
        <div className="px-5 pt-4">
          <InlineError message={error} />
        </div>
      )}
      {loading && !brief && (
        <div className="space-y-2 px-5 py-5" aria-hidden>
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
        </div>
      )}
      {!brief && !loading && !error && (
        <p className="px-5 py-4 text-sm text-slate-500">
          Generate a briefing to see what changed this week, what needs attention and who should act on it.
        </p>
      )}
      {brief && (
        <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1.6fr_1fr]" data-testid="briefing">
          <div className="min-w-0 space-y-4">
            <p className="text-base font-medium text-slate-900">{brief.headline}</p>
            {brief.highlights.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-slate-500">Highlights</p>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {brief.highlights.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              </div>
            )}
            {brief.concerns.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-slate-500">Needs attention</p>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {brief.concerns.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            )}
            {brief.actions.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-slate-500">Recommended actions</p>
                <ol className="space-y-2">
                  {brief.actions.map((a, i) => (
                    <li key={i} className="rounded-md border border-slate-200 px-3 py-2 text-sm">
                      <p className="font-medium text-slate-900">{a.action}</p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {a.owner} · {a.reason}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <SourceNote source={brief.source} model={brief.model} at={brief.generated_at} />
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-slate-500">Based on</p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400">
                  <th className="py-1 font-normal" />
                  <th className="py-1 text-right font-normal">This week</th>
                  <th className="py-1 text-right font-normal">Last week</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {METRIC_ROWS.map((r) => (
                  <tr key={r.key} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-600">{r.label}</td>
                    <td className="py-1.5 text-right font-medium text-slate-900">{fmtMetric(tw[r.key], r.pct)}</td>
                    <td className="py-1.5 text-right text-slate-500">{fmtMetric(lw[r.key], r.pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- learning difficulties (HOD + faculty)
function DifficultyItem({ d, courseId, teachingLinks }: { d: LearningDifficulty; courseId: string; teachingLinks: boolean }) {
  const q = encodeURIComponent(d.concept);
  return (
    <li className="rounded-md border border-slate-200 px-4 py-3" data-testid="difficulty">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="font-medium text-slate-900">{d.concept}</p>
        <p className="text-xs tabular-nums text-slate-500">
          {d.students_affected} of {d.students_attempted} students · {d.fail_rate}% of runs fail
          {d.hint_requests > 0 && ` · ${d.hint_requests} hints`}
        </p>
      </div>
      <p className="mt-1 text-sm text-slate-700">{d.explanation}</p>
      {d.example_questions.length > 0 && (
        <ul className="mt-2 space-y-0.5 border-l-2 border-slate-200 pl-3 text-sm italic text-slate-500">
          {d.example_questions.map((x, i) => <li key={i}>&ldquo;{x}&rdquo;</li>)}
        </ul>
      )}
      <p className="mt-2 text-sm text-slate-700">
        <span className="font-medium text-slate-900">Recommended: </span>
        {d.recommended_action}
      </p>
      <p className="mt-1.5 flex flex-wrap items-center gap-x-3 text-xs text-slate-400">
        <span>
          {d.practical_title} · <span className="font-mono">{d.tests.join(", ")}</span>
        </span>
        {teachingLinks && (
          <>
            <Link href={`/faculty/teaching?topic=${q}`} className="font-medium text-indigo-600 hover:text-indigo-800">
              Teaching notes
            </Link>
            <Link href={`/faculty/practicals/new?topic=${q}&course=${courseId}`} className="font-medium text-indigo-600 hover:text-indigo-800">
              Practice practical
            </Link>
          </>
        )}
      </p>
    </li>
  );
}

export function DifficultiesCard({ scope }: { scope: "hod" | "faculty" }) {
  const load = (refresh: boolean) => (scope === "hod" ? api.hodDifficulties(refresh) : api.facultyDifficulties(refresh));
  const { data, error, loading, setData } = useApi<LearningDifficulties>(() => load(false), [scope]);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  async function refresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      setData(await load(true));
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setRefreshing(false);
    }
  }

  const courses = data?.courses.filter((c) => c.difficulties.length > 0) ?? [];
  return (
    <Card>
      <CardHeader
        title={scope === "hod" ? "Learning difficulties" : "Where your students struggle"}
        subtitle="Concepts students find hardest, from failing tests, hint requests and tutor questions"
        action={
          <Button size="sm" variant="secondary" loading={refreshing} onClick={refresh} disabled={loading}>
            Re-analyse
          </Button>
        }
      />
      <div className="px-5 py-4">
        <InlineError message={error ?? refreshError} />
        {loading && !data && (
          <div className="space-y-2" aria-hidden>
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        )}
        {data && courses.length === 0 && <p className="text-sm text-slate-500">Not enough test activity yet to find patterns.</p>}
        <div className="space-y-6">
          {courses.map((c) => (
            <section key={c.course_id} data-testid={`difficulties-${c.course_code}`}>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">
                {c.course_code} · {c.course_title}
                {scope === "hod" && <span className="font-normal text-slate-500"> · {c.faculty_name ?? "No faculty assigned"}</span>}
              </h3>
              <ol className="space-y-2">
                {c.difficulties.map((d, i) => (
                  <DifficultyItem key={i} d={d} courseId={c.course_id} teachingLinks={scope === "faculty"} />
                ))}
              </ol>
            </section>
          ))}
        </div>
        {data && (
          <p className={cx("mt-4", courses.length === 0 && "hidden")}>
            <SourceNote source={data.source} model={data.model} at={data.generated_at} />
          </p>
        )}
      </div>
    </Card>
  );
}
