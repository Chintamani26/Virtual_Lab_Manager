"use client";

import { useMemo, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { cx } from "@/components/ui";
import type { ExecutionResult, TestResult, WorksheetAnswers, WorksheetCell, WorksheetSpec, WorksheetStep } from "@/lib/types";
import type { EditChange } from "@/lib/useProctoring";
import { checkStatus, num, parseAnswers, serializeAnswers, type CheckStatus } from "@/lib/worksheet";
import { DcBench } from "./DcBench";
import { NewtonFigure, ScatterGraph, SimpsonFigure } from "./Figures";
import { PendulumApparatus } from "./Pendulum";

type Typing = { recordChange: (c: EditChange) => void; recordKeystroke: () => void };

/**
 * The student's side of a worksheet lab (maths problems or a virtual experiment): no code, just values.
 * Everything is stored in answers.json; "Check" runs the lab's checks in the sandbox and each step / column shows
 * its own result until its value changes again.
 */
export function WorksheetView({
  spec,
  value,
  onChange,
  result,
  checkedValue,
  running,
  onCheck,
  readOnly = false,
  typing,
}: {
  spec: WorksheetSpec;
  /** answers.json */
  value: string;
  onChange: (v: string) => void;
  /** the latest check run (null before the first one) */
  result: ExecutionResult | null;
  /** answers.json as it was when `result` was produced */
  checkedValue: string | null;
  running: boolean;
  onCheck: () => void;
  readOnly?: boolean;
  typing?: Typing;
}) {
  const answers = useMemo(() => parseAnswers(value), [value]);
  const checked = useMemo(() => (checkedValue === null ? null : parseAnswers(checkedValue)), [checkedValue]);
  const tests = result && result.mode === "test" ? result.tests : undefined;
  const rowsFresh = !!checked && JSON.stringify(checked.rows) === JSON.stringify(answers.rows);
  const experiment = spec.kind === "experiment";

  function update(next: WorksheetAnswers) {
    onChange(serializeAnswers(next));
  }
  function typed(prev: string, next: string) {
    typing?.recordChange({ inserted: Math.max(0, next.length - prev.length), isFlush: false, isUndoRedo: false });
  }
  function setStep(id: string, v: string) {
    typed(answers.steps[id] ?? "", v);
    update({ ...answers, steps: { ...answers.steps, [id]: v } });
  }
  function setCell(row: number, key: string, v: string) {
    typed(String(answers.rows[row]?.[key] ?? ""), v);
    update({ ...answers, rows: answers.rows.map((r, i) => (i === row ? { ...r, [key]: v } : r)) });
  }
  function addRow(cells: Record<string, number>) {
    const blank = Object.fromEntries((spec.table?.columns ?? []).filter((c) => c.source === "student").map((c) => [c.key, ""]));
    update({ ...answers, rows: [...answers.rows, { ...blank, ...cells }] });
  }
  function removeRow(i: number) {
    update({ ...answers, rows: answers.rows.filter((_, j) => j !== i) });
  }

  const stepStatus = (s: WorksheetStep): CheckStatus => {
    if (!(answers.steps[s.id] ?? "").trim()) return null; // not answered yet: nothing to mark
    return checkStatus(tests, s.test, !!checked && (checked.steps[s.id] ?? "") === (answers.steps[s.id] ?? "") && (!experiment || rowsFresh));
  };

  const passed = tests?.filter((t) => t.passed).length ?? 0;

  return (
    <div className="h-full overflow-auto scroll-dark bg-surface-1" data-testid="worksheet">
      <div className="mx-auto max-w-4xl space-y-5 px-5 py-5">
        {experiment && spec.apparatus && (
          <Panel title="Apparatus" subtitle={spec.apparatus === "pendulum" ? "Simple pendulum" : "DC bench · Ohm's law"}>
            {spec.apparatus === "pendulum" ? (
              <PendulumApparatus
                config={spec.apparatus_config}
                onRecord={addRow}
                disabled={readOnly}
                full={!!spec.table && answers.rows.length >= spec.table.max_rows}
              />
            ) : (
              <DcBench
                config={spec.apparatus_config}
                onRecord={addRow}
                disabled={readOnly}
                full={!!spec.table && answers.rows.length >= spec.table.max_rows}
              />
            )}
          </Panel>
        )}

        {spec.table && (
          <Panel
            title={spec.table.title}
            subtitle={`${answers.rows.length} reading${answers.rows.length === 1 ? "" : "s"} · at least ${spec.table.min_rows}`}
          >
            <ObservationTable
              spec={spec}
              rows={answers.rows}
              readOnly={readOnly}
              onCell={setCell}
              onRemove={removeRow}
              onKey={() => typing?.recordKeystroke()}
              tests={tests}
              fresh={rowsFresh}
            />
          </Panel>
        )}

        {spec.graph && spec.table && (
          <Panel title={spec.graph.title} subtitle="Best-fit line updates as you fill in the table">
            <ScatterGraph
              points={answers.rows
                .map((r) => [num(r[spec.graph!.x]), num(r[spec.graph!.y])] as [number | null, number | null])
                .filter((p): p is [number, number] => p[0] !== null && p[1] !== null)}
              xLabel={spec.graph.x_label}
              yLabel={spec.graph.y_label}
            />
          </Panel>
        )}

        {spec.sections.map((sec) => (
          <Panel key={sec.id} title={sec.title}>
            {sec.body && (
              <div className="mb-4 text-sm">
                <Markdown dark>{sec.body}</Markdown>
              </div>
            )}
            <div className={cx("grid gap-5", sec.visual && "md:grid-cols-[minmax(0,1fr)_260px]")}>
              <ol className="space-y-3">
                {sec.steps.map((s, i) => {
                  return (
                    <StepRow
                      key={s.id}
                      n={i + 1}
                      step={s}
                      value={answers.steps[s.id] ?? ""}
                      status={stepStatus(s)}
                      readOnly={readOnly}
                      onChange={(v) => setStep(s.id, v)}
                      onKey={() => typing?.recordKeystroke()}
                    />
                  );
                })}
              </ol>
              {sec.visual === "newton" && (
                <NewtonFigure x1={num(answers.steps.nr_x1)} x2={num(answers.steps.nr_x2)} />
              )}
              {sec.visual === "simpson" && <SimpsonFigure />}
            </div>
            {!readOnly && (
              <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
                <button onClick={onCheck} disabled={running} className="btn btn-secondary" data-testid={`check-${sec.id}`}>
                  {running && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Check answers
                </button>
                {tests && (
                  <span className="text-xs text-fg-faint">
                    {passed} of {tests.length} checks correct in your last check
                  </span>
                )}
              </div>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-surface-2/60">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
        {subtitle && <span className="truncate text-xs text-fg-faint">{subtitle}</span>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

const inputBase =
  "h-8 rounded-ctl border bg-canvas px-2.5 font-mono text-sm text-fg outline-none transition placeholder:text-fg-faint/70 focus:border-brand-400 disabled:opacity-70";

function borderFor(status: CheckStatus): string {
  if (!status || status.state === "todo") return "border-line-strong";
  return status.state === "pass" ? "border-emerald-400/50" : "border-rose-400/60";
}

function StatusLine({ status }: { status: CheckStatus }) {
  if (!status) return null;
  if (status.state === "pass") return <p className="text-xs text-emerald-300">Correct</p>;
  if (status.state === "todo") return <p className="text-xs text-fg-faint">Not filled in yet</p>;
  return <p className="text-xs text-rose-300">{status.message}</p>;
}

function StepRow({
  n,
  step,
  value,
  status,
  readOnly,
  onChange,
  onKey,
}: {
  n: number;
  step: WorksheetStep;
  value: string;
  status: CheckStatus;
  readOnly: boolean;
  onChange: (v: string) => void;
  onKey: () => void;
}) {
  const id = `step-${step.id}`;
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1" data-testid={id}>
      <label htmlFor={id} className="min-w-0 text-sm text-fg">
        <span className="mr-2 font-mono text-xs text-fg-faint">Step {n}</span>
        {step.label}
      </label>
      <div className="flex items-center gap-2">
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKey}
          disabled={readOnly}
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          placeholder={step.placeholder || "answer"}
          aria-invalid={status?.state === "fail" || undefined}
          className={cx(inputBase, "w-32", borderFor(status))}
        />
        <span className="w-10 text-xs text-fg-faint">{step.unit}</span>
      </div>
      <div className="col-span-2">
        <StatusLine status={status} />
      </div>
    </li>
  );
}

function ObservationTable({
  spec,
  rows,
  readOnly,
  onCell,
  onRemove,
  onKey,
  tests,
  fresh,
}: {
  spec: WorksheetSpec;
  rows: Record<string, WorksheetCell>[];
  readOnly: boolean;
  onCell: (row: number, key: string, v: string) => void;
  onRemove: (row: number) => void;
  onKey: () => void;
  tests: TestResult[] | undefined;
  fresh: boolean;
}) {
  const table = spec.table!;
  const checks = [
    { name: table.test, label: "Readings" },
    ...table.columns.filter((c) => c.test).map((c) => ({ name: c.test, label: c.label })),
  ]
    .map((c) => ({ ...c, status: checkStatus(tests, c.name, fresh) }))
    .filter((c) => c.status);

  return (
    <div>
      <div className="overflow-x-auto scroll-dark">
        <table className="w-full min-w-[440px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-fg-faint">
              <th className="w-8 py-2 pr-2 font-normal">#</th>
              {table.columns.map((c) => (
                <th key={c.key} className="py-2 pr-3 font-normal">
                  {c.label}
                  {c.unit && <span className="text-fg-faint/70"> ({c.unit})</span>}
                </th>
              ))}
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={table.columns.length + 2} className="py-6 text-center text-xs text-fg-faint">
                  {spec.apparatus ? "No readings yet. Use the apparatus above and press Record reading." : "No rows yet."}
                </td>
              </tr>
            )}
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-line/60 last:border-0">
                <td className="py-1.5 pr-2 font-mono text-xs text-fg-faint">{i + 1}</td>
                {table.columns.map((c) => {
                  const status = c.test && String(r[c.key] ?? "").trim() ? checkStatus(tests, c.test, fresh) : null;
                  return (
                    <td key={c.key} className="py-1.5 pr-3">
                      {c.source === "apparatus" ? (
                        <span className="font-mono text-fg">{r[c.key] ?? "—"}</span>
                      ) : (
                        <input
                          value={String(r[c.key] ?? "")}
                          onChange={(e) => onCell(i, c.key, e.target.value)}
                          onKeyDown={onKey}
                          disabled={readOnly}
                          inputMode="decimal"
                          autoComplete="off"
                          spellCheck={false}
                          aria-label={`${c.label}, reading ${i + 1}`}
                          className={cx(inputBase, "w-24", borderFor(status))}
                        />
                      )}
                    </td>
                  );
                })}
                <td className="py-1.5 text-right">
                  {!readOnly && (
                    <button
                      onClick={() => onRemove(i)}
                      className="rounded-ctl px-1.5 py-0.5 text-xs text-fg-faint transition hover:bg-white/[0.05] hover:text-rose-300"
                      aria-label={`Remove reading ${i + 1}`}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {checks.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-line pt-3">
          {checks.map((c) => (
            <li key={c.name} className="flex gap-2 text-xs">
              <span className="w-40 shrink-0 truncate text-fg-faint">{c.label}</span>
              <StatusLine status={c.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
