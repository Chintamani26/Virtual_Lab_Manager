"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "@/components/ui";
import type { LintDiagnostic, LintResponse } from "@/lib/types";

/** Runtime label shown on the right of the status bar. */
function runtimeFor(file: string): string {
  if (file.endsWith(".py")) return "Python 3 · Judge0 sandbox";
  if (file.endsWith(".sim")) return "Logic simulator";
  if (file.endsWith(".ipynb")) return "Python notebook";
  if (file === "answers.json") return "Auto-checked worksheet";
  return "";
}

const SEVERITY_TEXT: Record<LintDiagnostic["severity"], string> = {
  error: "text-rose-300",
  warning: "text-amber-300",
  info: "text-sky-300",
};

function Tab({ active, onClick, children, testId }: { active: boolean; onClick: () => void; children: ReactNode; testId?: string }) {
  return (
    <button
      role="tab"
      aria-selected={active}
      data-testid={testId}
      onClick={onClick}
      className={cx(
        "relative flex h-10 shrink-0 items-center gap-2 px-3.5 text-xs transition-colors duration-150",
        active ? "text-fg" : "text-fg-faint hover:text-fg-muted",
      )}
    >
      {children}
      <span
        className={cx(
          "absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand-400 transition-opacity duration-200",
          active ? "opacity-100" : "opacity-0",
        )}
      />
    </button>
  );
}

function LintStatus({
  lint,
  loading,
  onJump,
}: {
  lint: LintResponse | undefined;
  loading: boolean;
  onJump?: (line: number, column: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const diags = lint?.diagnostics ?? [];
  const errors = diags.filter((d) => d.severity === "error").length;
  const warnings = diags.filter((d) => d.severity === "warning").length;
  const infos = diags.length - errors - warnings;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  useEffect(() => {
    if (diags.length === 0) setOpen(false);
  }, [diags.length]);

  const model = lint?.model ? (lint.model === "local" ? "local syntax" : lint.model) : "";

  let label: ReactNode;
  if (loading) {
    label = (
      <span className="inline-flex items-center gap-1.5 text-fg-faint">
        <Loader2 className="h-3 w-3 animate-spin" /> Checking…
      </span>
    );
  } else if (!lint) {
    label = <span className="text-fg-faint">Lint runs as you type</span>;
  } else if (diags.length === 0) {
    label = <span className="text-fg-faint">No issues</span>;
  } else {
    const parts = [
      errors && `${errors} error${errors === 1 ? "" : "s"}`,
      warnings && `${warnings} warning${warnings === 1 ? "" : "s"}`,
      infos && `${infos} note${infos === 1 ? "" : "s"}`,
    ].filter(Boolean);
    label = (
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cx(
          "-mx-1.5 rounded-ctl px-1.5 py-0.5 transition hover:bg-white/[0.06]",
          errors ? "text-rose-300" : warnings ? "text-amber-300" : "text-sky-300",
        )}
        data-testid="lint-summary"
      >
        {parts.join(" · ")}
      </button>
    );
  }

  return (
    <div ref={ref} className="relative flex min-w-0 items-center gap-2">
      {label}
      {model && !loading && (
        <span className="hidden truncate font-mono text-[10px] text-fg-faint sm:inline">
          {model}
          {lint?.cached ? " · cached" : ""}
        </span>
      )}
      {open && diags.length > 0 && (
        <div className="absolute bottom-full left-0 z-40 mb-2 w-[min(560px,80vw)] animate-fade-in rounded-lg border border-line-strong bg-surface-2 p-1.5 shadow-lg">
          <ul className="max-h-56 overflow-auto scroll-dark">
            {diags.map((d, i) => (
              <DiagRow
                key={i}
                d={d}
                onClick={() => {
                  onJump?.(d.line, d.column);
                  setOpen(false);
                }}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DiagRow({ d, onClick }: { d: LintDiagnostic; onClick: () => void }) {
  return (
    <li>
      <button onClick={onClick} className="flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-white/[0.05]">
        <span className={cx("w-12 shrink-0 font-mono text-[10.5px]", SEVERITY_TEXT[d.severity])}>{d.severity === "info" ? "note" : d.severity}</span>
        <span className="min-w-0 flex-1 text-fg">{d.message}</span>
        <span className="shrink-0 font-mono text-[10px] text-fg-faint">
          Ln {d.line}:{d.column} · {d.source}
        </span>
      </button>
    </li>
  );
}

/**
 * Left pane: Instructions + one tab per lab file (main.py / circuit.sim / data.ipynb),
 * the active file's content (children) and a fixed-height status bar (lint + runtime).
 */
export function MultiTabEditor({
  files,
  activeTab,
  onTabChange,
  lintByFile,
  lintLoading,
  onJump,
  engine,
  children,
}: {
  files: string[];
  activeTab: string;
  onTabChange: (tab: string) => void;
  lintByFile: Record<string, LintResponse>;
  lintLoading: boolean;
  onJump?: (line: number, column: number) => void;
  /** engine of the last execution, e.g. "judge0" / "local-python" */
  engine?: string;
  children: ReactNode;
}) {
  const isFile = activeTab !== "instructions";
  const runtime = !isFile
    ? ""
    : activeTab.endsWith(".py") && engine && engine !== "judge0" && engine !== "submission"
      ? `Python 3 · ${engine}`
      : runtimeFor(activeTab);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-stretch overflow-x-auto border-b border-line bg-surface-1 scroll-dark" role="tablist">
        <Tab active={activeTab === "instructions"} onClick={() => onTabChange("instructions")} testId="tab-instructions">
          Instructions
        </Tab>
        {files.map((f) => {
          const hasError = lintByFile[f]?.diagnostics.some((d) => d.severity === "error");
          return (
            <Tab key={f} active={activeTab === f} onClick={() => onTabChange(f)} testId={`tab-${f}`}>
              {f === "answers.json" ? <span>Worksheet</span> : <span className="font-mono">{f}</span>}
              {hasError && <span className="h-1.5 w-1.5 rounded-full bg-rose-500" title="Syntax error" />}
            </Tab>
          );
        })}
      </div>

      <div className="relative min-h-0 flex-1 bg-surface-1">{children}</div>

      <div className="flex h-8 shrink-0 items-center justify-between gap-3 border-t border-line bg-surface-1 px-3 text-[11px]">
        {isFile && activeTab !== "answers.json" ? (
          <LintStatus lint={lintByFile[activeTab]} loading={lintLoading} onJump={onJump} />
        ) : (
          <span />
        )}
        {runtime && <span className="hidden shrink-0 font-mono text-[10px] text-fg-faint md:inline">{runtime}</span>}
      </div>
    </div>
  );
}
