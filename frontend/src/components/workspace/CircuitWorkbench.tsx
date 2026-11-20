"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "@/components/ui";
import type { ExecutionResult, TestCaseSpec, TruthTableRow } from "@/lib/types";
import { TruthTable } from "./TruthTable";

function sameInputs(a: Record<string, number>, b: Record<string, number>) {
  return Object.keys(a).every((k) => Number(a[k]) === Number(b[k]));
}

function expectedFor(specs: TestCaseSpec[], inputs: Record<string, number>): Record<string, number> | null {
  const s = specs.find((t) => t.inputs && t.expected && sameInputs(t.inputs, inputs) && sameInputs(inputs, t.inputs));
  return s?.expected ?? null;
}

const STEP = 10; // svg units per truth-table row
const HI = 5;
const LO = 21;

/** One signal's square wave across all truth-table rows (time steps). */
function Wave({
  values,
  tone,
  mismatches,
  activeIndex,
}: {
  values: number[];
  tone: "input" | "output";
  mismatches?: boolean[];
  activeIndex: number;
}) {
  const w = values.length * STEP;
  let d = "";
  values.forEach((v, i) => {
    const y = v ? HI : LO;
    const x0 = i * STEP;
    d += i === 0 ? `M ${x0} ${y}` : ` L ${x0} ${y}`;
    d += ` L ${x0 + STEP} ${y}`;
  });
  const area = values.map((v, i) => (v ? `M ${i * STEP} ${HI} H ${(i + 1) * STEP} V ${LO} H ${i * STEP} Z` : "")).join(" ");
  const color = tone === "input" ? "#7dd3fc" : "#a78bfa";
  return (
    <svg viewBox={`0 0 ${w} 26`} preserveAspectRatio="none" className="h-7 w-full" aria-hidden>
      {activeIndex >= 0 && <rect x={activeIndex * STEP} y={0} width={STEP} height={26} fill="rgb(99 102 241 / 0.14)" />}
      {mismatches?.map((m, i) => (m ? <rect key={i} x={i * STEP} y={0} width={STEP} height={26} fill="rgb(244 63 94 / 0.18)" /> : null))}
      {area && <path d={area} fill={color} fillOpacity={0.12} />}
      <path d={d} fill="none" stroke={color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" strokeLinejoin="miter" />
      {values.map((_, i) =>
        i > 0 ? <line key={i} x1={i * STEP} x2={i * STEP} y1={0} y2={26} stroke="rgb(255 255 255 / 0.05)" vectorEffect="non-scaling-stroke" /> : null,
      )}
    </svg>
  );
}

/**
 * Interactive results view for circuit.sim labs, driven by the last simulation's truth table:
 * input toggles → output LEDs, a digital timing diagram, and the colour-coded truth table.
 */
export function CircuitWorkbench({
  result,
  specs,
  stale,
  running,
  onSimulate,
}: {
  result: ExecutionResult | null;
  specs: TestCaseSpec[];
  stale: boolean;
  running: boolean;
  onSimulate: () => void;
}) {
  const table: TruthTableRow[] = result?.truth_table ?? [];
  const inputs = table.length ? Object.keys(table[0].inputs) : [];
  const outputs = table.length ? Object.keys(table[0].outputs) : [];
  const signature = inputs.join(",") + "|" + outputs.join(",");

  const [vals, setVals] = useState<Record<string, number>>({});
  useEffect(() => {
    setVals(Object.fromEntries(inputs.map((k) => [k, 0])));
    // reset only when the circuit's pins change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  const activeIndex = useMemo(() => table.findIndex((r) => sameInputs(r.inputs, vals)), [table, vals]);
  const row = activeIndex >= 0 ? table[activeIndex] : null;
  const expected = row ? expectedFor(specs, row.inputs) : null;

  if (!table.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center" data-testid="circuit-workbench-empty">
        <p className="text-sm text-fg-faint">Simulate to see the truth table and timing.</p>
        <button onClick={onSimulate} disabled={running} className="btn btn-secondary">
          {running && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Simulate
        </button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto scroll-dark p-3" data-testid="circuit-workbench">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-medium text-fg-muted">Simulation</h3>
        {stale && (
          <span className="text-xs text-amber-300" data-testid="workbench-stale">
            Out of date
          </span>
        )}
        <button onClick={onSimulate} disabled={running} className="btn btn-ghost ml-auto">
          {running && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Simulate again
        </button>
      </div>

      {/* live I/O */}
      <div className={cx("mt-3 grid gap-3 sm:grid-cols-2", stale && "opacity-70")}>
        <div className="rounded-lg border border-line bg-surface-2 p-3">
          <p className="mb-2 text-xs text-fg-faint">Inputs</p>
          <div className="flex flex-wrap gap-2">
            {inputs.map((k) => {
              const on = vals[k] === 1;
              return (
                <button
                  key={k}
                  role="switch"
                  aria-checked={on}
                  data-testid={`toggle-${k}`}
                  onClick={() => setVals((v) => ({ ...v, [k]: on ? 0 : 1 }))}
                  className="flex items-center gap-2 rounded-md border border-line bg-canvas px-2 py-1.5 transition hover:border-line-strong"
                >
                  <span className={cx("relative h-4 w-7 rounded-full transition-colors duration-150", on ? "bg-sky-500" : "bg-white/[0.1]")}>
                    <span className={cx("absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all duration-150", on ? "left-[14px]" : "left-0.5")} />
                  </span>
                  <span className="font-mono text-xs text-fg">{k}</span>
                  <span className={cx("font-mono text-xs", on ? "text-sky-300" : "text-fg-faint")}>{on ? 1 : 0}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="rounded-lg border border-line bg-surface-2 p-3">
          <p className="mb-2 text-xs text-fg-faint">Outputs</p>
          <div className="flex flex-wrap gap-3">
            {outputs.map((k) => {
              const v = row ? row.outputs[k] : 0;
              const exp = expected ? expected[k] : undefined;
              const wrong = exp !== undefined && Number(exp) !== Number(v);
              return (
                <div key={k} className="flex items-center gap-2" data-testid={`led-${k}`} data-on={v === 1 ? "1" : "0"}>
                  <span
                    className={cx(
                      "h-4 w-4 rounded-full ring-2 transition-all duration-200",
                      v === 1 ? "bg-emerald-400" : "bg-emerald-950",
                      wrong ? "ring-rose-500" : "ring-white/10",
                    )}
                  />
                  <span className="font-mono text-xs text-fg">{k}</span>
                  <span className={cx("font-mono text-xs", wrong ? "text-rose-300" : "text-fg-muted")}>
                    {v}
                    {wrong && <span className="ml-1 text-[10px]">(expected {exp})</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* timing diagram */}
      <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3" data-testid="waveform">
        <p className="mb-2 flex items-baseline justify-between gap-3 text-xs text-fg-faint">
          <span>Timing</span>
          <span className="text-[11px]">Click a step to load its inputs</span>
        </p>
        <div className="grid grid-cols-[3.5rem_minmax(0,1fr)] items-center gap-x-2">
          {inputs.map((k) => (
            <WaveRow key={k} name={k} tone="input">
              <Wave values={table.map((r) => r.inputs[k])} tone="input" activeIndex={activeIndex} />
            </WaveRow>
          ))}
          <div className="col-span-2 my-1 h-px bg-line" />
          {outputs.map((k) => (
            <WaveRow key={k} name={k} tone="output">
              <Wave
                values={table.map((r) => r.outputs[k])}
                tone="output"
                activeIndex={activeIndex}
                mismatches={table.map((r) => {
                  const e = expectedFor(specs, r.inputs);
                  return !!e && e[k] !== undefined && Number(e[k]) !== Number(r.outputs[k]);
                })}
              />
            </WaveRow>
          ))}
          <span />
          <div className="flex">
            {table.map((r, i) => (
              <button
                key={i}
                onClick={() => setVals({ ...r.inputs })}
                className={cx(
                  "h-5 flex-1 rounded-[3px] font-mono text-[9.5px] transition",
                  i === activeIndex ? "bg-brand/25 text-indigo-200" : "text-fg-faint hover:bg-white/[0.05]",
                )}
                title={Object.entries(r.inputs).map(([k, v]) => `${k}=${v}`).join(" ")}
              >
                t{i}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* truth table */}
      <div className="mt-3">
        <TruthTable rows={table} specs={specs} />
      </div>
    </div>
  );
}

function WaveRow({ name, tone, children }: { name: string; tone: "input" | "output"; children: React.ReactNode }) {
  return (
    <>
      <span className={cx("truncate text-right font-mono text-[11px]", tone === "input" ? "text-sky-300" : "text-violet-300")}>{name}</span>
      <div className="min-w-0">{children}</div>
    </>
  );
}
