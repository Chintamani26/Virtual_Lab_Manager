"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { DarkSkeleton, cx, modKey } from "@/components/ui";
import { LAB_FILE } from "@/lib/api";
import { isUnanswered } from "@/lib/worksheet";
import type { ExecutionResult, ExecutionStatus, LabType, TestResult } from "@/lib/types";
import type { RunKind } from "./types";

export interface ExpectedActual {
  label: string | null;
  expected: string;
  actual: string;
}

/**
 * Pull "expected X, got Y" pairs out of assertion/circuit messages, e.g.
 *   "duplicates must be ignored: expected size 3, got 6"
 *   "for A=0, B=0, CIN=1: SUM expected 1, got 0; COUT expected 1, got 0"
 */
export function parseExpectedActual(message: string | null): ExpectedActual[] {
  if (!message) return [];
  const out: ExpectedActual[] = [];
  const re = /(?:\b([A-Za-z_]\w*)\s+)?expected\s+(.+?),?\s+got\s+([^;\n]+)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(message)) !== null) {
    const label = m[1] && !/^(ignored|be|is|was|should)$/i.test(m[1]) ? m[1] : null;
    out.push({ label, expected: m[2].trim(), actual: m[3].trim().replace(/[.\s]+$/, "") });
  }
  return out;
}

function splitError(message: string): { kind: string | null; text: string } {
  const m = /^([A-Z][A-Za-z]+(?:Error|Exception)|CircuitError|TimeoutError):\s*(.*)$/s.exec(message);
  return m ? { kind: m[1], text: m[2] } : { kind: null, text: message };
}

type Tone = "neutral" | "pass" | "warn" | "fail";
const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-fg-muted",
  pass: "text-emerald-300",
  warn: "text-amber-300",
  fail: "text-rose-300",
};

const RUN_SUMMARY: Record<ExecutionStatus, string> = {
  ok: "Run finished",
  error: "Run failed",
  timeout: "Time limit exceeded",
  compile_error: "Syntax error",
};

/** "4/5 passed", plus why a run stopped early. */
function summaryOf(r: ExecutionResult): string {
  if (r.mode !== "test") return RUN_SUMMARY[r.status] ?? r.summary;
  let s = `${r.tests_passed}/${r.tests_total} passed`;
  if (r.engine === "submission") s += ", incl. hidden";
  if (r.status === "timeout") s += " · time limit exceeded";
  else if (r.status === "compile_error") s += " · code failed to load";
  return s;
}

function TestRow({ t, open, onToggle, label }: { t: TestResult; open: boolean; onToggle: () => void; label?: string }) {
  const diff = useMemo(() => parseExpectedActual(t.message), [t.message]);
  const err = t.message ? splitError(t.message) : null;
  const todo = !!label && !t.passed && isUnanswered(t.message); // worksheet step not filled in yet
  const expandable = !t.passed && !!t.message && !todo;
  return (
    <li className={cx("rounded-md", !t.passed && !todo && "bg-rose-500/[0.05]")} data-testid={`test-row-${t.name}`}>
      <button
        onClick={expandable ? onToggle : undefined}
        aria-expanded={expandable ? open : undefined}
        className={cx("flex h-8 w-full items-center gap-2 rounded-md px-2 text-left", expandable && "hover:bg-white/[0.03]")}
      >
        <ChevronRight
          className={cx(
            "h-3.5 w-3.5 shrink-0 text-fg-faint transition-transform duration-150",
            open && "rotate-90",
            !expandable && "invisible",
          )}
        />
        <span
          className={cx("min-w-0 truncate", label ? "text-[13px]" : "font-mono text-[12.5px]", t.passed ? "text-fg-muted" : "text-fg")}
          title={label ? t.name : undefined}
        >
          {label ?? t.name}
        </span>
        {t.hidden && (
          <span className="shrink-0 text-[11px] text-fg-faint" title="Hidden test, runs on submission">
            hidden
          </span>
        )}
        <span
          className={cx(
            "ml-auto shrink-0 font-mono text-[11px] font-medium",
            t.passed ? "text-emerald-400" : todo ? "text-fg-faint" : "text-rose-400",
          )}
        >
          {t.passed ? "PASS" : todo ? "TO DO" : "FAIL"}
        </span>
      </button>
      {expandable && open && err && (
        <div className="pb-3 pl-[2.125rem] pr-3">
          <p className="font-mono text-[12px] leading-5 text-fg-muted">
            {err.kind && !label && <span className="text-rose-300">{err.kind}: </span>}
            {err.text}
          </p>
          {diff.length > 0 && (
            <div className="mt-2 overflow-hidden rounded-md border border-line bg-canvas" data-testid="expected-actual">
              {diff.map((d, i) => (
                <div key={i} className={cx("font-mono text-[12px] leading-6", i > 0 && "border-t border-line")}>
                  <div className="flex gap-3 px-3 text-emerald-300">
                    <span className="w-16 shrink-0 select-none text-fg-faint">expected</span>
                    {d.label && <span className="text-fg-faint">{d.label}</span>}
                    <span className="min-w-0 break-all">{d.expected}</span>
                  </div>
                  <div className="flex gap-3 px-3 text-rose-300">
                    <span className="w-16 shrink-0 select-none text-fg-faint">actual</span>
                    {d.label && <span className="text-fg-faint">{d.label}</span>}
                    <span className="min-w-0 break-all">{d.actual}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function Output({ label, text, tone, defaultOpen }: { label: string; text: string; tone: "fg" | "rose"; defaultOpen: boolean }) {
  return (
    <details open={defaultOpen} className="group mt-2 rounded-md border border-line bg-canvas/60">
      <summary className="flex h-7 cursor-pointer list-none items-center gap-1.5 px-2.5 text-[11px] text-fg-faint hover:text-fg-muted">
        <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
        {label}
        <span className="text-fg-faint/70">· {text.split("\n").length} lines</span>
      </summary>
      <pre className={cx("max-h-48 overflow-auto scroll-dark whitespace-pre-wrap px-3 pb-2.5 font-mono text-[12px] leading-5", tone === "rose" ? "text-rose-300" : "text-fg")}>
        {text}
      </pre>
    </details>
  );
}

/** Top half of the results pane: test results and program output. */
export function TestRunnerTerminal({
  result,
  running,
  labType,
  expectedCount,
  submitted = false,
  labels,
}: {
  result: ExecutionResult | null;
  running: RunKind | null;
  labType: LabType;
  /** number of skeleton rows to show while running (visible tests) */
  expectedCount: number;
  /** exam submitted (read-only): nothing can be run any more */
  submitted?: boolean;
  /** worksheet labs: readable check names (test name -> description) */
  labels?: Record<string, string>;
}) {
  const worksheet = labType === "worksheet";
  const failing = useMemo(() => (result ? result.tests.filter((t) => !t.passed).map((t) => t.name) : []), [result]);
  const [open, setOpen] = useState<Set<string>>(new Set());
  useEffect(() => setOpen(new Set(failing)), [failing]);

  const isRunning = running !== null;
  const allPassed = !!result && result.tests_total > 0 && result.tests_passed === result.tests_total;
  const tone: Tone = !result
    ? "neutral"
    : result.mode === "test"
      ? allPassed
        ? "pass"
        : result.tests_passed === 0
          ? "fail"
          : "warn"
      : result.status === "ok"
        ? "neutral"
        : "fail";
  const file = LAB_FILE[labType];
  const skeletonRows = Math.max(3, Math.min(expectedCount || 5, 9));

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="test-runner">
      <div className="panel-header">
        {isRunning ? (
          <span className="inline-flex items-center gap-1.5 text-fg-muted" data-testid="test-summary">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {running === "submit"
              ? worksheet
                ? "Checking every answer…"
                : "Running all tests…"
              : running === "test"
                ? worksheet
                  ? "Checking…"
                  : "Running tests…"
                : `Running ${file}…`}
          </span>
        ) : result ? (
          <span className={cx("font-mono text-[12.5px] font-semibold", TONE_TEXT[tone])} data-testid="test-summary">
            {summaryOf(result)}
          </span>
        ) : (
          <span data-testid="test-summary">{worksheet ? "Checks" : "Tests"}</span>
        )}
        {result && !isRunning && result.engine !== "submission" && (
          <span className="ml-auto truncate font-mono text-[11px] font-normal text-fg-faint">
            <span className="hidden sm:inline">{result.engine} · </span>
            {result.duration_ms} ms
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto scroll-dark bg-canvas/40 px-2 py-2">
        {isRunning ? (
          <div className="space-y-1 px-2 pt-1" aria-hidden>
            {Array.from({ length: running === "run" ? 3 : skeletonRows }).map((_, i) => (
              <div key={i} className="flex h-8 items-center gap-2 px-2">
                <DarkSkeleton className="h-3 w-48 max-w-[60%]" />
                <DarkSkeleton className="ml-auto h-3 w-8" />
              </div>
            ))}
          </div>
        ) : !result ? (
          <p className="px-3 py-2 text-sm text-fg-faint">
            {submitted
              ? "Submitted. Your score is in the Rubric tab."
              : worksheet
                ? `Press Check answers to see which steps are right (${modKey()}+Enter).`
                : `Run tests to check ${file} (${modKey()}+Enter).`}
          </p>
        ) : (
          <div className="animate-fade-in">
            {result.mode === "test" && (
              <ul className="space-y-0.5">
                {result.tests.map((t) => (
                  <TestRow
                    key={t.name}
                    t={t}
                    label={worksheet ? (labels?.[t.name] ?? (t.hidden ? "Hidden check" : undefined)) : undefined}
                    open={open.has(t.name)}
                    onToggle={() =>
                      setOpen((s) => {
                        const n = new Set(s);
                        if (n.has(t.name)) n.delete(t.name);
                        else n.add(t.name);
                        return n;
                      })
                    }
                  />
                ))}
              </ul>
            )}
            <div className="px-2">
              {result.stdout && <Output label="stdout" text={result.stdout} tone="fg" defaultOpen={result.mode === "run"} />}
              {result.stderr && <Output label="stderr" text={result.stderr} tone="rose" defaultOpen={result.status !== "ok"} />}
              {labType === "circuit" && result.truth_table && (
                <p className="mt-2 text-xs text-fg-faint">The truth table and timing are in the simulation panel.</p>
              )}
              {labType === "notebook" && result.cell_outputs && result.cell_outputs.length > 0 && (
                <p className="mt-2 text-xs text-fg-faint">
                  {result.cell_outputs.length} cell{result.cell_outputs.length === 1 ? "" : "s"} ran. Outputs are shown in {file}.
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
