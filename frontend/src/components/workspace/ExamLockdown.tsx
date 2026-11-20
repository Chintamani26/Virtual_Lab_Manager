"use client";

/**
 * Exam lockdown screens for the student workspace (docs/API.md v1.2):
 *   ExamGate            instructions + acknowledgement + "Start exam in fullscreen" (replaces ProctorGate on lockdown labs)
 *   SebRequiredGate     "must be taken in Safe Exam Browser" + sebs:// launch link
 *   ExamLockOverlay     locked → waiting for mentor · unlocked → Resume · held by another tab
 * After submitting, the read-only notice is SubmittedBanner (RubricScorecard.tsx), shared with proctored labs.
 * There is no way out to another role from these screens: a locked student waits for their faculty,
 * who unlocks from the Live Lab Monitor in their own session.
 */

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { cx } from "@/components/ui";
import type { ExamState, LockdownMode, StudentPractical } from "@/lib/types";
import type { ExamPhase } from "@/lib/useExamLockdown";
import { StartGate, submitRule, type GateSection } from "./StartGate";

const SEB_DOWNLOAD = "https://safeexambrowser.org/download_en.html";
const SAFE_SEB_URL = /^(https?|sebs?):\/\//i;

function fmtClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Opaque full-screen backdrop; the workspace stays hidden behind it. */
function Backdrop({
  children,
  testId,
  phase,
  z = "z-[85]",
}: {
  children: React.ReactNode;
  testId: string;
  phase?: string;
  z?: string;
}) {
  return (
    <div className={cx("fixed inset-0 flex items-center justify-center overflow-y-auto bg-canvas p-4", z)} data-testid={testId} data-phase={phase}>
      {children}
    </div>
  );
}

const card = "w-full animate-fade-in rounded-lg border border-line-strong bg-surface-1 p-6 text-fg";

// ---------------------------------------------------------------- gate
export function ExamGate({
  practical,
  mode,
  sebDetected,
  sebVersion,
  heldElsewhere,
  starting,
  error,
  onStart,
}: {
  practical: StudentPractical;
  mode: LockdownMode;
  sebDetected: boolean;
  sebVersion: string | null;
  heldElsewhere: boolean;
  starting: boolean;
  error: string | null;
  onStart: () => void;
}) {
  const b = (t: string) => <b className="font-medium text-fg">{t}</b>;
  const sections: GateSection[] = [
    {
      title: "Before you start",
      ordered: true,
      items: [
        "Close other apps and turn off notifications.",
        "The exam opens in fullscreen. Stay on this page until you submit.",
      ],
    },
    {
      title: "Your exam locks if you",
      tone: "fail",
      items: [
        "switch to another tab, window or app",
        "leave fullscreen or open developer tools",
        "open the exam in a second tab, or reload or close this page",
      ],
      note: "A locked exam stays locked until your mentor unlocks it.",
    },
    {
      title: "During the exam",
      items: [
        "Copy, paste and right-click are turned off.",
        "Your typing and every lock are recorded for your faculty.",
        ...((practical.exam?.max_breaks ?? 0) > 0
          ? [
              <>
                Need a break? Press {b("Pause")} before you leave: up to {practical.exam!.max_breaks} breaks of{" "}
                {Math.round((practical.exam!.break_limit_s ?? 600) / 60)} minutes each. Your work is hidden while you&apos;re away.
              </>,
            ]
          : []),
        <>{b("Run tests")} and {b("Hint")} work as usual. Hints never give the answer.</>,
        submitRule(practical),
        <>You can submit {b("only once")}. Submitting ends the exam.</>,
      ],
    },
  ];
  return (
    <StartGate
      heading="This lab is an exam"
      practical={practical}
      modeLabel={
        mode === "seb" ? (
          <span className={sebDetected ? "text-emerald-300" : "text-amber-300"} title={sebVersion ?? undefined}>
            {sebDetected ? "Safe Exam Browser detected" : "Safe Exam Browser"}
          </span>
        ) : (
          "Strict exam mode"
        )
      }
      sections={sections}
      notices={
        <>
          {heldElsewhere && (
            <p
              className="rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
              data-testid="exam-held-elsewhere"
            >
              This exam is already open in another tab or window. Starting here locks it. Close the other tab, or continue there.
            </p>
          )}
          {error && <p className="rounded-lg border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</p>}
        </>
      }
      ackLabel="I have read these rules"
      startLabel="Start exam in fullscreen"
      starting={starting}
      onStart={onStart}
      testId="exam-gate"
      startTestId="exam-start"
    />
  );
}

// ---------------------------------------------------------------- Safe Exam Browser
export function SebRequiredGate({
  title,
  launchUrl,
  rejected,
}: {
  title: string;
  launchUrl: string | null | undefined;
  /** SEB is running, but its Config Key did not match this exam */
  rejected: boolean;
}) {
  return (
    <Backdrop testId="seb-gate" z="z-[80]">
      <div className={cx(card, "max-w-lg")}>
        <h2 className="text-base font-semibold">Open this exam in Safe Exam Browser</h2>
        <p className="mt-0.5 truncate text-xs text-fg-faint">{title}</p>
        <p className="mt-4 text-sm text-fg-muted">
          This exam must be taken in Safe Exam Browser (SEB), which locks your computer to the exam until you submit.
        </p>

        {rejected ? (
          <p className="mt-4 rounded-lg border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-sm text-rose-200" data-testid="seb-rejected">
            Safe Exam Browser is running, but its configuration doesn&apos;t match this exam. Quit SEB and open the exam with the
            configuration link from your mentor.
          </p>
        ) : (
          <ol className="mt-4 list-decimal space-y-1.5 pl-5 text-sm text-fg-muted marker:text-fg-faint">
            <li>
              Install Safe Exam Browser from{" "}
              <a href={SEB_DOWNLOAD} target="_blank" rel="noreferrer" className="text-brand-400 hover:underline">
                safeexambrowser.org
              </a>
              .
            </li>
            <li>{launchUrl ? "Click Open in Safe Exam Browser below." : "Open the exam configuration (.seb) file your mentor shared."}</li>
            <li>Sign in inside SEB, open this lab and start the exam.</li>
          </ol>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-end gap-2">
          <Link href="/student" className="btn btn-ghost">
            Back
          </Link>
          <a href={SEB_DOWNLOAD} target="_blank" rel="noreferrer" className="btn btn-secondary">
            Get SEB
          </a>
          {launchUrl && SAFE_SEB_URL.test(launchUrl) && (
            <a href={launchUrl} className="btn btn-primary" data-testid="seb-launch">
              Open in Safe Exam Browser
            </a>
          )}
        </div>
      </div>
    </Backdrop>
  );
}

// ---------------------------------------------------------------- locked / resume / elsewhere
export function ExamLockOverlay({
  phase,
  state,
  starting,
  error,
  onResume,
}: {
  phase: Extract<ExamPhase, "locked" | "resume" | "elsewhere">;
  state: ExamState;
  starting: boolean;
  error: string | null;
  onResume: () => void;
}) {
  return (
    <Backdrop testId="exam-lock-overlay" phase={phase}>
      <div className={cx(card, "max-w-sm")}>
        {phase === "locked" && (
          <>
            <h2 className="text-base font-semibold">Exam locked</h2>
            <p className="mt-3 text-sm text-rose-200" data-testid="exam-lock-reason">
              {state.lock_reason ?? "Exam rule violation"}
            </p>
            <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 text-xs">
              <div>
                <dt className="text-fg-faint">Locked at</dt>
                <dd className="mt-0.5 font-mono tabular-nums text-fg">{fmtClock(state.locked_at)}</dd>
              </div>
              <div>
                <dt className="text-fg-faint">Violations</dt>
                <dd className="mt-0.5 font-mono tabular-nums text-fg" data-testid="exam-violations">
                  {state.violations}
                </dd>
              </div>
            </dl>
            <p className="mt-4 border-t border-line pt-4 text-sm text-amber-200" data-testid="exam-waiting">
              Waiting for your mentor to unlock.
            </p>
            {(state.max_breaks ?? 0) - (state.breaks_used ?? 0) > 0 && (
              <p className="mt-3 text-xs text-fg-faint" data-testid="exam-pause-tip">
                Need to step away next time? Press <b className="font-medium text-fg-muted">Pause</b> first, so it counts
                as a break instead of locking the exam. You have {(state.max_breaks ?? 0) - (state.breaks_used ?? 0)} of{" "}
                {state.max_breaks} breaks left.
              </p>
            )}
          </>
        )}

        {phase === "resume" && (
          <>
            <h2 className="text-base font-semibold">Your mentor unlocked your exam</h2>
            <p className="mt-2 text-sm text-fg-muted">
              Return to fullscreen to continue. Leaving again locks the exam again, so press Pause first if you need a
              break.
            </p>
            {state.violations > 0 && (
              <p className="mt-2 text-xs text-fg-faint">
                {state.violations} violation{state.violations === 1 ? "" : "s"} recorded
              </p>
            )}
            {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}
            <div className="mt-6 flex justify-end">
              <button onClick={onResume} disabled={starting} className="btn btn-primary" data-testid="exam-resume">
                {starting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Resume exam
              </button>
            </div>
          </>
        )}

        {phase === "elsewhere" && (
          <>
            <h2 className="text-base font-semibold">Exam open in another tab</h2>
            <p className="mt-2 text-sm text-fg-muted">Only one tab can hold this exam. Close this tab and continue in the other one.</p>
            <div className="mt-6 flex justify-end">
              <Link href="/student" className="btn btn-secondary">
                Back to labs
              </Link>
            </div>
          </>
        )}
      </div>
    </Backdrop>
  );
}
