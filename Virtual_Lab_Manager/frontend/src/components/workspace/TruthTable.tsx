"use client";

import { cx } from "@/components/ui";
import type { TestCaseSpec, TruthTableRow } from "@/lib/types";

function sameInputs(a: Record<string, number>, b: Record<string, number>) {
  const ka = Object.keys(a);
  return ka.length === Object.keys(b).length && ka.every((k) => Number(a[k]) === Number(b[k]));
}

/**
 * Renders the simulated truth table. Rows whose inputs match a test case spec are coloured:
 * matching expected outputs → green, mismatching → red; other rows stay neutral.
 */
export function TruthTable({
  rows,
  specs,
  dark = true,
}: {
  rows: TruthTableRow[];
  specs: TestCaseSpec[];
  dark?: boolean;
}) {
  if (rows.length === 0) return null;
  const inputCols = Object.keys(rows[0].inputs);
  const outputCols = Object.keys(rows[0].outputs);
  const circuitSpecs = specs.filter((s) => s.inputs && s.expected);

  return (
    <div className={cx("overflow-x-auto rounded-lg border", dark ? "border-line" : "border-slate-200")}>
      <table className="w-full text-center font-mono text-xs">
        <thead className={dark ? "bg-surface-2 text-fg-faint" : "bg-slate-50 text-slate-600"}>
          <tr>
            {inputCols.map((c) => (
              <th key={`i-${c}`} className="px-3 py-1.5 font-medium">
                {c}
              </th>
            ))}
            <th className={cx("w-px px-0", dark ? "bg-line-strong" : "bg-slate-200")} />
            {outputCols.map((c) => (
              <th key={`o-${c}`} className={cx("px-3 py-1.5 font-semibold", dark ? "text-fg" : "text-slate-900")}>
                {c}
              </th>
            ))}
            <th className="px-3 py-1.5 font-medium">Check</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const spec = circuitSpecs.find((s) => sameInputs(s.inputs!, r.inputs));
            const mismatches = spec
              ? Object.entries(spec.expected!).filter(([k, v]) => Number(r.outputs[k]) !== Number(v)).map(([k]) => k)
              : [];
            const status = spec ? (mismatches.length === 0 ? "pass" : "fail") : "none";
            return (
              <tr
                key={i}
                className={cx(
                  "border-t",
                  dark ? "border-line" : "border-slate-100",
                  status === "pass" && (dark ? "bg-emerald-500/10" : "bg-emerald-50"),
                  status === "fail" && (dark ? "bg-rose-500/10" : "bg-rose-50"),
                )}
              >
                {inputCols.map((c) => (
                  <td key={c} className={cx("px-3 py-1", dark ? "text-fg-muted" : "text-slate-700")}>
                    {r.inputs[c]}
                  </td>
                ))}
                <td className={cx("w-px px-0", dark ? "bg-line-strong" : "bg-slate-200")} />
                {outputCols.map((c) => (
                  <td
                    key={c}
                    className={cx(
                      "px-3 py-1 font-semibold",
                      mismatches.includes(c)
                        ? "text-rose-400"
                        : dark
                          ? "text-fg"
                          : "text-slate-900",
                    )}
                    title={mismatches.includes(c) && spec ? `expected ${spec.expected![c]}` : undefined}
                  >
                    {r.outputs[c]}
                    {mismatches.includes(c) && spec && (
                      <span className="ml-1 text-[10px] font-normal text-rose-400/80">≠{spec.expected![c]}</span>
                    )}
                  </td>
                ))}
                <td className="px-3 py-1 text-[11px]">
                  {status === "pass" ? (
                    <span className="text-emerald-400">✓</span>
                  ) : status === "fail" ? (
                    <span className="text-rose-400">✗</span>
                  ) : (
                    <span className={dark ? "text-fg-faint" : "text-slate-400"}>·</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
