"use client";

import { Markdown } from "@/components/Markdown";
import type { StudentPractical } from "@/lib/types";

/** Instructions tab: lab brief, visible test cases (+ hidden count) and the grading rubric. */
export function InstructionsView({ practical }: { practical: StudentPractical }) {
  const visible = practical.test_cases.filter((t) => !t.hidden);
  const totalPoints = practical.rubric.reduce((a, r) => a + r.max_points, 0);
  const worksheet = practical.lab_type === "worksheet";
  return (
    <div className="h-full animate-fade-in overflow-auto scroll-dark bg-surface-1 px-6 py-5">
      <div className="mx-auto max-w-3xl">
        <Markdown dark>{practical.description}</Markdown>

        <h3 className="mt-8 text-sm font-semibold text-fg">
          {worksheet ? "What is checked" : "Tests"} <span className="ml-1 font-normal text-fg-faint">{visible.length}</span>
        </h3>
        <ul className="mt-3 space-y-2">
          {visible.map((t) => (
            <li key={t.name} className="rounded-lg border border-line bg-surface-2 p-3">
              {worksheet ? (
                <p className="text-sm text-fg">{t.description || t.name}</p>
              ) : (
                <>
                  <p className="font-mono text-xs text-fg">{t.name}</p>
                  {t.description && <p className="mt-1 text-xs text-fg-muted">{t.description}</p>}
                </>
              )}
              {t.code && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[11px] text-fg-faint hover:text-fg-muted">Show test code</summary>
                  <pre className="mt-2 overflow-x-auto rounded-md border border-line bg-canvas p-2 font-mono text-[11px] leading-5 text-fg-muted">
                    {t.code}
                  </pre>
                </details>
              )}
              {t.inputs && t.expected && (
                <p className="mt-2 font-mono text-[11px] text-fg-muted">
                  {Object.entries(t.inputs)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(" ")}{" "}
                  →{" "}
                  <span className="text-emerald-300">
                    {Object.entries(t.expected)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(" ")}
                  </span>
                </p>
              )}
            </li>
          ))}
          {practical.hidden_test_count > 0 && (
            <li className="px-1 text-xs text-fg-faint">
              +{practical.hidden_test_count} hidden {worksheet ? "check" : "test"}
              {practical.hidden_test_count === 1 ? "" : "s"} run on submission.
            </li>
          )}
        </ul>

        {practical.rubric.length > 0 && (
          <>
            <h3 className="mt-8 text-sm font-semibold text-fg">
              Rubric{" "}
              <span className="ml-1 font-normal text-fg-faint">
                {totalPoints} pts{totalPoints !== practical.max_score ? `, scaled to ${practical.max_score}` : ""}
              </span>
            </h3>
            <ul className="mt-3 space-y-2">
              {practical.rubric.map((r) => (
                <li key={r.id} className="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface-2 p-3">
                  <div>
                    <p className="text-sm text-fg">{r.name}</p>
                    {r.description && <p className="mt-0.5 text-xs text-fg-faint">{r.description}</p>}
                  </div>
                  <span className="shrink-0 font-mono text-xs text-fg-muted">{r.max_points} pts</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
