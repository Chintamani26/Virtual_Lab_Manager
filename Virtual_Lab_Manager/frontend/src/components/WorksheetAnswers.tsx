"use client";

import { useMemo } from "react";
import { cx } from "@/components/ui";
import type { TestResult, WorksheetSpec } from "@/lib/types";
import { parseAnswers } from "@/lib/worksheet";

/** Read-only, light view of a worksheet submission for faculty: readings table and step answers with their checks. */
export function WorksheetAnswers({
  spec,
  value,
  results,
}: {
  spec: WorksheetSpec;
  value: string;
  results: TestResult[];
}) {
  const answers = useMemo(() => parseAnswers(value), [value]);
  const byName = new Map(results.map((r) => [r.name, r]));
  const mark = (test: string | null) => {
    const r = test ? byName.get(test) : undefined;
    if (!r) return null;
    return r.passed ? (
      <span className="text-xs font-medium text-emerald-700">Correct</span>
    ) : (
      <span className="text-xs font-medium text-rose-700">Wrong</span>
    );
  };

  return (
    <div className="h-full space-y-6 overflow-auto p-5">
      {spec.table && (
        <section>
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-900">{spec.table.title}</h3>
            <span className="text-xs text-slate-500">{answers.rows.length} readings</span>
          </div>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                  <th className="py-2 pr-3 font-medium">#</th>
                  {spec.table.columns.map((c) => (
                    <th key={c.key} className="py-2 pr-3 font-medium">
                      {c.label}
                      {c.unit && ` (${c.unit})`}
                      {c.source === "apparatus" && <span className="font-normal text-slate-400"> · measured</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {answers.rows.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100 last:border-0">
                    <td className="py-1.5 pr-3 font-mono text-xs text-slate-400">{i + 1}</td>
                    {spec.table!.columns.map((c) => (
                      <td key={c.key} className="py-1.5 pr-3 font-mono tabular-nums text-slate-800">
                        {r[c.key] === "" || r[c.key] === null || r[c.key] === undefined ? "—" : String(r[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            {[{ test: spec.table.test, label: "Readings" }, ...spec.table.columns.filter((c) => c.test).map((c) => ({ test: c.test, label: c.label }))].map(
              (c) =>
                mark(c.test) && (
                  <span key={c.label} className="text-xs text-slate-500">
                    {c.label}: {mark(c.test)}
                  </span>
                ),
            )}
          </div>
        </section>
      )}

      {spec.sections.map((sec) => (
        <section key={sec.id}>
          <h3 className="text-sm font-semibold text-slate-900">{sec.title}</h3>
          <ol className="mt-2 divide-y divide-slate-100">
            {sec.steps.map((s, i) => {
              const n = i + 1;
              const v = answers.steps[s.id] ?? "";
              return (
                <li key={s.id} className="flex items-baseline gap-3 py-2">
                  <span className="w-12 shrink-0 font-mono text-xs text-slate-400">Step {n}</span>
                  <span className="min-w-0 flex-1 text-sm text-slate-700">{s.label}</span>
                  <span className={cx("shrink-0 font-mono text-sm tabular-nums", v ? "text-slate-900" : "text-slate-400")}>
                    {v || "blank"} {v && s.unit}
                  </span>
                  <span className="w-14 shrink-0 text-right">{mark(s.test)}</span>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
