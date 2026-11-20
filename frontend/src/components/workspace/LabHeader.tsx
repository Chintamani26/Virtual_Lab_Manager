"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { cx, modKey } from "@/components/ui";
import { fmtDate, relativeDue } from "@/lib/api";
import type { ExecutionResult, LockdownMode, ProctorSummary, StudentPractical } from "@/lib/types";
import { ProctorChip } from "./Proctoring";
import type { RunKind, SaveState } from "./types";

/** Compact test status (dot + count) with a reserved minimum width so it rarely shifts the header. */
function TestStatus({ result, running, noun }: { result: ExecutionResult | null; running: RunKind | null; noun: string }) {
  const box = "inline-flex min-w-[8.5rem] items-center gap-1.5 whitespace-nowrap text-xs";
  if (running === "test" || running === "submit") {
    return (
      <span className={cx(box, "text-fg-muted")} data-testid="status-pill">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {running === "submit" ? "Grading…" : noun === "checks" ? "Checking…" : "Running tests…"}
      </span>
    );
  }
  if (!result) {
    return (
      <span className={cx(box, "text-fg-faint")} data-testid="status-pill">
        {noun === "checks" ? "Not checked yet" : "No test run yet"}
      </span>
    );
  }
  if (result.mode === "run") {
    const ok = result.status === "ok";
    return (
      <span className={cx(box, ok ? "text-fg-muted" : "text-rose-300")} data-testid="status-pill">
        {ok ? "Run finished" : "Run failed"}
      </span>
    );
  }
  const { tests_passed: p, tests_total: t } = result;
  const tone = t > 0 && p === t ? "pass" : p === 0 ? "fail" : "warn";
  return (
    <span
      className={cx(box, "font-mono text-fg-muted")}
      data-testid="status-pill"
      title={result.engine === "submission" ? "Includes hidden tests" : undefined}
    >
      <span
        className={cx("h-1.5 w-1.5 shrink-0 rounded-full", tone === "pass" ? "bg-emerald-400" : tone === "warn" ? "bg-amber-400" : "bg-rose-400")}
      />
      {p}/{t} {noun} passing
    </span>
  );
}

function SaveIndicator({ save }: { save: SaveState }) {
  if (save.state === "saving") return <span>Saving…</span>;
  if (save.state === "error") return <span className="text-rose-300">Save failed</span>;
  if (save.state === "dirty") return <span>Unsaved</span>;
  if (save.at) return <span title={`Draft saved ${fmtDate(save.at, true)}`}>Saved {shortTime(save.at)}</span>;
  return null;
}

/** "11:51" for today, "19 Nov" otherwise — keeps the header meta line short. */
function shortTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function LabHeader({
  practical,
  result,
  running,
  hintLoading,
  save,
  proctored,
  proctorSummary,
  onRun,
  onRunTests,
  onAskTutor,
  onSubmit,
  exam,
  actionsDisabled = false,
  lockNav = false,
  onPause,
  pauseBlocked,
}: {
  practical: StudentPractical;
  result: ExecutionResult | null;
  running: RunKind | null;
  hintLoading: boolean;
  save: SaveState;
  proctored: boolean;
  proctorSummary: ProctorSummary;
  onRun: () => void;
  onRunTests: () => void;
  onAskTutor: () => void;
  onSubmit: () => void;
  /** exam-lockdown labs: chip label + lock count */
  exam?: { mode: LockdownMode; violations: number } | null;
  /** exam locked / submitted / not started: Run, Run tests, Hint and Submit are disabled */
  actionsDisabled?: boolean;
  /** live exam: navigating away would lock the exam, so the back link becomes plain text */
  lockNav?: boolean;
  /** Pause button (proctored labs once started, live exams); omitted = no button */
  onPause?: () => void;
  /** why Pause is unavailable (e.g. no breaks left); null = available */
  pauseBlocked?: string | null;
}) {
  const due = relativeDue(practical.due_at);
  const busy = running !== null || actionsDisabled;
  const worksheet = practical.lab_type === "worksheet"; // values, not code: nothing to "run", only to check
  const mod = modKey();

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface-1 px-3 sm:px-4">
      <div className="min-w-0 flex-1 leading-tight">
        <nav className="flex min-w-0 items-center gap-1.5 text-sm" aria-label="Breadcrumb">
          {lockNav ? (
            <span className="shrink-0 font-mono text-fg-faint" title="Leaving this page locks your exam">
              {practical.course_code}
            </span>
          ) : (
            <Link
              href={`/student/courses/${practical.course_id}`}
              className="shrink-0 font-mono text-fg-muted transition-colors hover:text-fg"
              title={`Back to ${practical.course_title}`}
            >
              {practical.course_code}
            </Link>
          )}
          <span className="text-fg-faint/60" aria-hidden>
            /
          </span>
          <h1 className="truncate font-medium text-fg">{practical.title}</h1>
        </nav>
        <p className="mt-0.5 flex items-center gap-1.5 truncate text-[11px] text-fg-faint">
          <span
            className={cx("shrink-0", due.tone === "late" && "text-rose-300", due.tone === "soon" && "text-amber-300")}
            title={practical.due_at ? `Due ${fmtDate(practical.due_at, true)}` : undefined}
          >
            {practical.due_at ? due.label : "No deadline"}
          </span>
          {(save.at || save.state !== "clean") && (
            <span className="hidden sm:inline">
              · <SaveIndicator save={save} />
            </span>
          )}
        </p>
      </div>

      <div className="hidden md:block">
        <TestStatus result={result} running={running} noun={worksheet ? "checks" : "tests"} />
      </div>
      {proctored && (
        <div className="hidden md:block">
          <ProctorChip summary={proctorSummary} exam={exam} />
        </div>
      )}

      <div className="flex shrink-0 items-center gap-1.5">
        {onPause && (
          <button
            onClick={onPause}
            disabled={running !== null || !!pauseBlocked}
            className="btn btn-ghost"
            title={pauseBlocked ?? "Take a break: your work is saved and hidden until you resume"}
            data-testid="pause-button"
          >
            Pause
          </button>
        )}
        {!worksheet && (
          <button onClick={onRun} disabled={busy} className="btn btn-ghost hidden sm:inline-flex" title="Run the program">
            {running === "run" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Run
          </button>
        )}
        <button
          onClick={onRunTests}
          disabled={busy}
          className="btn btn-secondary"
          title={worksheet ? `Check your answers (${mod}+Enter)` : `Run tests (${mod}+Enter)`}
        >
          {running === "test" && !hintLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {worksheet ? "Check answers" : "Run tests"}
        </button>
        <button
          onClick={onAskTutor}
          disabled={busy || hintLoading}
          className="btn btn-secondary"
          title={worksheet ? "Get a hint for a step that isn't right yet" : "Get a hint for a failing test"}
        >
          {hintLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Hint
        </button>
        <button
          onClick={onSubmit}
          disabled={busy}
          className="btn btn-primary"
          title={worksheet ? "Check every answer, including hidden checks, and grade" : "Run all tests, including hidden ones, and grade"}
        >
          {running === "submit" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Submit
        </button>
      </div>
    </header>
  );
}
