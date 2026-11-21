"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { Loader2, X } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { DarkSkeleton } from "@/components/ui";
import { fmtDate, fmtScore } from "@/lib/api";
import type { Submission } from "@/lib/types";

/** One row per rubric criterion: name, score, feedback. */
function CriterionRows({ submission }: { submission: Submission }) {
  return (
    <ul className="divide-y divide-line rounded-lg border border-line">
      {submission.rubric_breakdown.map((r) => (
        <li key={r.criterion_id} className="px-3 py-2.5">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-fg">{r.name}</span>
            <span className="shrink-0 font-mono tabular-nums text-fg-muted">
              {fmtScore(r.score)}/{r.max_points}
            </span>
          </div>
          {r.feedback && <p className="mt-1 text-xs leading-relaxed text-fg-faint">{r.feedback}</p>}
        </li>
      ))}
    </ul>
  );
}

/** "5/5 tests · 2/2 hidden · auto-graded · gemini-2.5-flash" */
function metaLine(s: Submission): string {
  const hidden = s.test_results.filter((t) => t.hidden);
  const parts = [`${s.tests_passed}/${s.tests_total} tests`];
  if (hidden.length > 0) parts.push(`${hidden.filter((t) => t.passed).length}/${hidden.length} hidden`);
  if (s.rubric_score !== null && s.faculty_score !== null) parts.push(`AI ${fmtScore(s.rubric_score)}, faculty ${fmtScore(s.faculty_score)}`);
  parts.push(gradedBy(s));
  return parts.join(" · ");
}

function gradedBy(s: Submission) {
  const model = s.grading_model ?? "";
  if (s.status === "reviewed") return "reviewed by faculty";
  if (model === "rules") return "auto-graded · offline rubric";
  return model ? `auto-graded · ${model}` : "auto-graded";
}

function Feedback({ text }: { text: string }) {
  return (
    <div>
      <h3 className="text-xs font-medium text-fg-muted">Feedback</h3>
      <Markdown dark className="mt-1.5">
        {text}
      </Markdown>
    </div>
  );
}

/** Where "Exit" goes once the work is handed in: the student home (To do / Completed). */
export const EXIT_HREF = "/student";

/** Modal shown right after submitting: score, per-criterion rows and feedback. */
export function RubricScorecardModal({
  submission,
  loading,
  onClose,
  onViewBreakdown,
  exitLabel = "Exit lab",
}: {
  submission: Submission | null;
  loading: boolean;
  onClose: () => void;
  onViewBreakdown: () => void;
  exitLabel?: string;
}) {
  const primaryRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!loading) primaryRef.current?.focus();
  }, [loading]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !loading && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loading, onClose]);

  const score = submission ? (submission.final_score ?? submission.rubric_score) : null;

  return (
    <div
      className="fixed inset-0 z-[75] flex animate-fade-in items-center justify-center bg-canvas/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Rubric scorecard"
      data-testid="scorecard-modal"
    >
      <div className="flex max-h-[88vh] w-full max-w-[520px] flex-col overflow-hidden rounded-lg border border-line-strong bg-surface-1 text-fg shadow-lg">
        <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4">
          <h2 className="text-sm font-semibold">{loading ? "Grading" : "Score"}</h2>
          {!loading && (
            <button onClick={onClose} className="btn btn-ghost ml-auto h-7 w-7 px-0" aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-auto scroll-dark p-5">
          {loading || !submission ? (
            <div data-testid="grading-loading">
              <p className="flex items-center gap-2 text-sm text-fg-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Running all tests and scoring the rubric. This takes a few seconds.
              </p>
              <div className="mt-5 space-y-2" aria-hidden>
                <DarkSkeleton className="h-10 w-32" />
                {[0, 1, 2].map((i) => (
                  <DarkSkeleton key={i} className="h-12 w-full rounded-lg" />
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div>
                <p className="font-mono text-4xl font-semibold tabular-nums tracking-tight">
                  <span data-testid="scorecard-score">{fmtScore(score)}</span>
                  <span className="text-xl text-fg-faint">/{submission.max_score}</span>
                </p>
                <p className="mt-1.5 text-xs text-fg-faint">{metaLine(submission)}</p>
              </div>
              {submission.rubric_breakdown.length > 0 && <CriterionRows submission={submission} />}
              {submission.ai_feedback && <Feedback text={submission.ai_feedback} />}
            </div>
          )}
        </div>

        {!loading && (
          <div className="flex h-14 shrink-0 items-center justify-end gap-2 border-t border-line px-4">
            <button onClick={onViewBreakdown} className="btn btn-ghost" data-testid="view-breakdown">
              View breakdown
            </button>
            <Link ref={primaryRef} href={EXIT_HREF} className="btn btn-primary" data-testid="scorecard-exit">
              {exitLabel}
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

/** Bottom drawer (tab 2): persistent rubric view — survives reloads via latest_submission. */
export function RubricPanel({ submission }: { submission: Submission | null }) {
  if (!submission) {
    return (
      <p className="px-3 py-3 text-sm text-fg-faint" data-testid="rubric-empty">
        Submit to see your rubric score.
      </p>
    );
  }
  const score = submission.final_score ?? submission.rubric_score;
  return (
    <div className="h-full space-y-4 overflow-auto scroll-dark p-3" data-testid="rubric-panel">
      <div>
        <p className="font-mono text-2xl font-semibold tabular-nums tracking-tight">
          {fmtScore(score)}
          <span className="text-base text-fg-faint">/{submission.max_score}</span>
        </p>
        <p className="mt-1 text-xs text-fg-faint">
          Submitted {fmtDate(submission.submitted_at, true)} · {metaLine(submission)}
        </p>
      </div>
      {submission.rubric_breakdown.length > 0 && <CriterionRows submission={submission} />}
      {submission.ai_feedback && <Feedback text={submission.ai_feedback} />}
      {submission.faculty_comment && (
        <div>
          <h3 className="text-xs font-medium text-fg-muted">Faculty comment</h3>
          <p className="mt-1.5 text-sm text-fg">{submission.faculty_comment}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Bar shown once the work is handed in (exam, or proctored lab): the workspace is read-only.
 * Exit goes back to the student home. A proctored lab with submissions left offers
 * Keep working, which opens a new proctored session.
 */
export function SubmittedBanner({
  message,
  exitLabel = "Exit lab",
  onKeepWorking,
  testId = "submitted-banner",
}: {
  message: string;
  exitLabel?: string;
  onKeepWorking?: () => void;
  testId?: string;
}) {
  return (
    // centered over the editor pane on desktop (grid is 1.32fr : 1fr), so the results pane stays readable
    <div className="pointer-events-none absolute inset-x-0 bottom-12 z-40 flex justify-center px-4 lg:right-[43.1%]">
      <div
        role="status"
        data-testid={testId}
        className="pointer-events-auto flex max-w-xl animate-rise-in items-center gap-3 rounded-lg border border-emerald-400/30 bg-emerald-950 py-1.5 pl-3.5 pr-1.5 text-sm text-emerald-100 shadow-lg"
      >
        <span className="min-w-0">{message}</span>
        <div className="flex shrink-0 items-center gap-1">
          {onKeepWorking && (
            <button
              onClick={onKeepWorking}
              className="inline-flex h-7 items-center rounded-ctl px-2.5 text-xs font-medium text-emerald-100/80 hover:bg-emerald-400/10 hover:text-emerald-50"
              data-testid="keep-working"
            >
              Keep working
            </button>
          )}
          <Link
            href={EXIT_HREF}
            className="inline-flex h-7 items-center rounded-ctl border border-emerald-300/40 bg-emerald-400/15 px-2.5 text-xs font-medium text-emerald-50 hover:bg-emerald-400/25"
            data-testid="submitted-exit"
          >
            {exitLabel}
          </Link>
        </div>
      </div>
    </div>
  );
}

/**
 * In-app submit confirmation. Replaces window.confirm(), which makes browsers exit fullscreen —
 * that used to be recorded as a proctoring "fullscreen exit" on every honest submission.
 */
export function ConfirmSubmitDialog({
  hiddenTests,
  endsExam = false,
  onCancel,
  onConfirm,
}: {
  hiddenTests: number;
  /** exam-lockdown labs: submitting ends the exam and makes the workspace read-only */
  endsExam?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  const tests = hiddenTests > 0 ? `all tests, including ${hiddenTests} hidden ${hiddenTests === 1 ? "one" : "ones"}` : "all tests";
  return (
    <div
      className="fixed inset-0 z-[75] flex animate-fade-in items-center justify-center bg-canvas/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm submission"
      data-testid="confirm-submit"
    >
      <div className="w-full max-w-sm rounded-lg border border-line-strong bg-surface-1 p-5 text-fg shadow-lg">
        <h2 className="text-base font-semibold">Submit for grading?</h2>
        <p className="mt-2 text-sm text-fg-muted">
          {endsExam
            ? `This runs ${tests}, grades your work and ends the exam.`
            : `This runs ${tests}${hiddenTests > 0 ? "," : ""} and grades your work.`}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="btn btn-ghost">
            Cancel
          </button>
          <button ref={confirmRef} onClick={onConfirm} className="btn btn-primary" data-testid="confirm-submit-button">
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
