"use client";

import type { ExecutionResult, RubricScore, TestResult } from "@/lib/types";
import { ScoreBar, cx } from "./ui";
import { fmtScore } from "@/lib/api";

export function TestResultsList({ tests }: { tests: TestResult[] }) {
  if (tests.length === 0) return <p className="px-5 py-4 text-sm text-slate-500">No test results.</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {tests.map((t) => (
        <li key={t.name} className="px-5 py-2.5">
          <div className="flex items-center gap-2 text-sm">
            <span className="min-w-0 truncate font-mono text-xs text-slate-800">{t.name}</span>
            {t.hidden && <span className="text-xs text-slate-400">hidden</span>}
            <span className={cx("ml-auto shrink-0 text-xs font-medium", t.passed ? "text-emerald-700" : "text-rose-700")}>
              {t.passed ? "Passed" : "Failed"}
            </span>
          </div>
          {!t.passed && t.message && (
            <pre className="mt-1.5 whitespace-pre-wrap rounded-md bg-slate-50 px-2 py-1.5 font-mono text-[11px] text-rose-700">
              {t.message}
            </pre>
          )}
        </li>
      ))}
    </ul>
  );
}

export function RubricBreakdown({ items }: { items: RubricScore[] }) {
  if (items.length === 0) return <p className="px-5 py-4 text-sm text-slate-500">No rubric breakdown.</p>;
  return (
    <ul className="space-y-4 px-5 py-4">
      {items.map((r) => (
        <li key={r.criterion_id}>
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-900">{r.name}</span>
            <span className="tabular-nums text-slate-700">
              {fmtScore(r.score)}/{r.max_points}
            </span>
          </div>
          <div className="mt-1.5">
            <ScoreBar value={r.score} max={r.max_points} />
          </div>
          {r.feedback && <p className="mt-1.5 text-xs text-slate-500">{r.feedback}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Compact light-theme execution summary (used for faculty validation runs). */
export function ExecutionSummary({ result }: { result: ExecutionResult }) {
  const allPassed = result.tests_total > 0 && result.tests_passed === result.tests_total;
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5">
        <span
          className={cx(
            "text-sm font-medium",
            result.status !== "ok" ? "text-rose-700" : allPassed ? "text-emerald-700" : "text-amber-700",
          )}
        >
          {result.summary}
        </span>
        <span className="font-mono text-xs text-slate-500">
          {result.engine} · {result.duration_ms} ms · {result.status}
        </span>
      </div>
      <TestResultsList tests={result.tests} />
      {(result.stdout || result.stderr) && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap border-t border-slate-100 bg-slate-50 px-4 py-2 font-mono text-[11px] text-slate-700">
          {result.stdout}
          {result.stderr && <span className="text-rose-700">{result.stderr}</span>}
        </pre>
      )}
    </div>
  );
}
