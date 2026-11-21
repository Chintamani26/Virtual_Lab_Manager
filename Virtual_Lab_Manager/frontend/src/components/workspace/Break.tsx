"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "@/components/ui";

/** Exam breaks are limited by the server; proctored-lab breaks are only recorded. */
export interface BreakRules {
  exam: boolean;
  /** breaks left, including the one about to start (exam only) */
  left: number;
  max: number;
  /** a break longer than this locks the exam (exam only) */
  limitS: number;
}

function clock(totalS: number): string {
  const s = Math.max(0, Math.floor(totalS));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** "Take a break?" — says exactly what happens before the student leaves. */
export function BreakDialog({
  rules,
  error,
  onCancel,
  onConfirm,
}: {
  rules: BreakRules;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const mins = Math.round(rules.limitS / 60);
  const n = rules.max - rules.left + 1;
  return (
    <div className="fixed inset-0 z-[90] flex animate-fade-in items-center justify-center bg-canvas/80 p-4" role="dialog" aria-modal="true" aria-labelledby="break-title" data-testid="break-dialog">
      <div className="w-full max-w-md rounded-lg border border-line-strong bg-surface-1 p-6 text-fg shadow-lg">
        <h2 id="break-title" className="text-base font-semibold">
          Take a break?
        </h2>
        <ul className="mt-4 list-disc space-y-1.5 pl-5 text-sm text-fg-muted marker:text-fg-faint">
          <li>Your work is saved and hidden until you come back.</li>
          {rules.exam ? (
            <>
              <li>
                This is break <b className="font-medium text-fg">{n} of {rules.max}</b>. You can leave this tab, the
                fullscreen, or close the page without locking the exam.
              </li>
              <li>
                Come back within <b className="font-medium text-fg">{mins} minutes</b>. After that the exam locks and
                your mentor has to unlock it.
              </li>
            </>
          ) : (
            <li>Time away during a break is recorded as a break, not as leaving the lab.</li>
          )}
          <li>Your faculty can see when and how long you were on a break.</li>
        </ul>
        {error && <p className="mt-4 rounded-lg border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onCancel} className="btn btn-ghost">
            Keep working
          </button>
          <button onClick={onConfirm} className="btn btn-primary" data-testid="break-confirm">
            Start break
          </button>
        </div>
      </div>
    </div>
  );
}

/** Full-screen "On break" card with a timer; the workspace stays hidden behind it. */
export function BreakOverlay({
  since,
  rules,
  breakNumber,
  resuming,
  error,
  onResume,
  onTimeUp,
}: {
  /** break start, ms since epoch */
  since: number;
  rules: BreakRules;
  breakNumber: number;
  resuming: boolean;
  error: string | null;
  onResume: () => void;
  /** exam: the limit has passed (ask the server, which locks the exam) */
  onTimeUp?: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const elapsedS = (now - since) / 1000;
  const leftS = rules.limitS - elapsedS;
  const over = rules.exam && leftS <= 0;
  useEffect(() => {
    if (over) onTimeUp?.();
    // fire once when the limit passes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [over]);
  const warn = rules.exam && leftS <= 120;

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center overflow-y-auto bg-canvas p-4" data-testid="break-overlay">
      <div className="w-full max-w-sm animate-fade-in rounded-lg border border-line-strong bg-surface-1 p-6 text-fg">
        <h2 className="text-base font-semibold">On break</h2>
        <p className="mt-1 text-xs text-fg-faint">
          {rules.exam ? `Break ${breakNumber} of ${rules.max}` : "Your break is being recorded"}
        </p>

        {rules.exam ? (
          <div className="mt-5">
            <p className="text-xs text-fg-faint">Time left</p>
            <p className={cx("mt-1 font-mono text-4xl tabular-nums", warn ? "text-amber-300" : "text-fg")} data-testid="break-timer">
              {clock(leftS)}
            </p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className={cx("h-full rounded-full transition-[width] duration-500", warn ? "bg-amber-400" : "bg-brand-400")}
                style={{ width: `${Math.max(0, Math.min(100, (leftS / rules.limitS) * 100))}%` }}
              />
            </div>
          </div>
        ) : (
          <div className="mt-5">
            <p className="text-xs text-fg-faint">Away for</p>
            <p className="mt-1 font-mono text-4xl tabular-nums text-fg" data-testid="break-timer">
              {clock(elapsedS)}
            </p>
          </div>
        )}

        <p className="mt-5 text-sm text-fg-muted">
          {rules.exam
            ? "Your work is saved and hidden. You can leave this page; come back here and press Resume before the time runs out."
            : "Your work is saved and hidden. Press Resume when you're ready to continue in fullscreen."}
        </p>
        {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}
        <div className="mt-6 flex justify-end">
          <button onClick={onResume} disabled={resuming || over} className="btn btn-primary" data-testid="break-resume">
            {resuming && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {rules.exam ? "Resume exam" : "Resume lab"}
          </button>
        </div>
      </div>
    </div>
  );
}
