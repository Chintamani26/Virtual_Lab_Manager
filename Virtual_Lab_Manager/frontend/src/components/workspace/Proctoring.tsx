"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cx } from "@/components/ui";
import type { LockdownMode, ProctorSummary, StudentPractical } from "@/lib/types";
import type { Proctoring } from "@/lib/useProctoring";
import { StartGate, submitRule, type GateSection } from "./StartGate";

export function fmtDuration(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** Compact header chip: mode label + live counters; hover/focus reveals the full log.
 *  On exam-lockdown labs it reads "Exam mode" / "SEB exam". */
export function ProctorChip({
  summary,
  exam,
}: {
  summary: ProctorSummary;
  exam?: { mode: LockdownMode; violations: number } | null;
}) {
  const flagged =
    summary.paste_blocked + summary.copy_blocked + summary.devtools_blocked + summary.focus_lost + (exam?.violations ?? 0) > 0;
  const label = exam ? (exam.mode === "seb" ? "SEB exam" : "Exam mode") : "Proctored";
  const rows: [string, string | number][] = [
    ...(exam
      ? ([
          ["Lockdown", exam.mode === "seb" ? "Safe Exam Browser" : "Strict exam mode"],
          ["Exam locks", exam.violations],
        ] as [string, string | number][])
      : []),
    ["Sessions", summary.sessions],
    ["Paste attempts blocked", summary.paste_blocked],
    ["Copy / cut attempts blocked", summary.copy_blocked],
    ["Tab / window switches", summary.focus_lost],
    ["Time away", fmtDuration(summary.time_away_ms)],
    ["Fullscreen exits", summary.fullscreen_exits],
    ["Developer-tools attempts", summary.devtools_blocked],
    ["Large insertions", summary.large_insertions],
  ];
  return (
    <div className="group relative" tabIndex={0} data-testid="proctor-chip">
      <span className={cx("pill cursor-default", flagged ? "pill-warn" : "pill-neutral")}>
        <span className="hidden xl:inline" data-testid="proctor-chip-label">
          {label}
        </span>
        <span className="hidden h-3 w-px bg-current opacity-20 xl:inline" />
        <span className="tabular-nums" title="Paste attempts blocked">
          <span data-testid="proctor-paste-count">{summary.paste_blocked}</span> {plural(summary.paste_blocked, "paste", "pastes")}
        </span>
        <span className="opacity-40">·</span>
        <span className="tabular-nums" title="Tab / window switches">
          <span data-testid="proctor-focus-count">{summary.focus_lost}</span> {plural(summary.focus_lost, "switch", "switches")}
        </span>
        {exam && exam.violations > 0 && (
          <>
            <span className="opacity-40">·</span>
            <span className="tabular-nums" title="Exam locks">
              {exam.violations} {plural(exam.violations, "lock", "locks")}
            </span>
          </>
        )}
      </span>
      <div className="invisible absolute right-0 top-full z-[70] mt-2 w-72 rounded-lg border border-line-strong bg-surface-2 p-3 text-xs text-fg-muted opacity-0 shadow-lg transition duration-150 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
        <p className="mb-2 font-medium text-fg">Proctoring log</p>
        <dl className="space-y-1">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3">
              <dt>{k}</dt>
              <dd className="font-mono tabular-nums text-fg">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 border-t border-line pt-2 text-[11px] text-fg-faint">Your faculty sees this log with your submission.</p>
      </div>
    </div>
  );
}

export function ProctorGate({ proctoring, practical }: { proctoring: Proctoring; practical: StudentPractical }) {
  const [starting, setStarting] = useState(false);
  const limit = practical.submission_limit;
  const used = practical.submissions_used ?? 0;
  const b = (t: string) => <b className="font-medium text-fg">{t}</b>;
  const sections: GateSection[] = [
    {
      title: "Before you start",
      ordered: true,
      items: [
        "Close other apps and turn off notifications.",
        "The lab opens in fullscreen. Stay on this page while you work.",
      ],
    },
    {
      title: "While you work",
      items: [
        practical.lab_type === "worksheet"
          ? "Copy, paste and right-click are turned off. Type your own answers."
          : "Copy, paste, drag-and-drop and right-click are turned off. Type your own work.",
        "Leaving fullscreen, switching tabs or windows and opening developer tools are recorded.",
        "Your typing activity is recorded to show the work is your own.",
        "Your faculty sees this record with your submission.",
        <>Need a break? Press {b("Pause")} before you step away, so the time is recorded as a break.</>,
      ],
    },
    {
      title: "Testing and submitting",
      items: [
        "Your work saves automatically, so you can stop and continue later.",
        practical.lab_type === "worksheet" ? (
          <>{b("Check answers")} shows which steps are right. It does not count as a submission.</>
        ) : (
          <>{b("Run tests")} checks your work against the visible tests. It does not count as a submission.</>
        ),
        submitRule(practical),
        ...(limit
          ? [`You can submit up to ${limit} times${used > 0 ? ` (${used} used so far)` : ""}. Your best score counts.`]
          : []),
        <>Stuck? {b("Hint")} asks you guiding questions. It never gives the answer.</>,
      ],
    },
  ];
  return (
    <StartGate
      heading="Proctored lab"
      practical={practical}
      modeLabel="Proctored"
      sections={sections}
      ackLabel="I have read these instructions"
      startLabel="Start proctored session"
      starting={starting}
      onStart={async () => {
        setStarting(true);
        try {
          await proctoring.start();
        } finally {
          setStarting(false);
        }
      }}
      testId="proctor-gate"
    />
  );
}

/** Floating notices (absolute, so they never push the panes around). */
export function FloatingNotice({
  tone,
  children,
  onDismiss,
  action,
}: {
  tone: "warn" | "fail";
  children: React.ReactNode;
  onDismiss?: () => void;
  action?: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className={cx(
        "pointer-events-auto flex max-w-xl animate-rise-in items-center gap-2 rounded-lg border px-3.5 py-2 text-sm shadow-lg",
        tone === "warn" ? "border-amber-400/30 bg-amber-950 text-amber-100" : "border-rose-400/30 bg-rose-950 text-rose-100",
      )}
    >
      <span className="min-w-0">{children}</span>
      {action}
      {onDismiss && (
        <button onClick={onDismiss} className="ml-1 rounded-ctl p-0.5 opacity-70 hover:opacity-100" aria-label="Dismiss">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
