"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { cx } from "@/components/ui";
import { fmtDate } from "@/lib/api";
import type { StudentPractical } from "@/lib/types";

export interface GateSection {
  title: string;
  items: ReactNode[];
  /** numbered steps instead of bullets */
  ordered?: boolean;
  /** rose heading: things that have consequences (e.g. what locks an exam) */
  tone?: "fail";
  /** one line under the list */
  note?: ReactNode;
}

/**
 * Shared "read this before you start" screen for proctored labs (ProctorGate) and exams (ExamGate):
 * lab facts on top, short titled sections, then an acknowledgement that enables the start button.
 * Opaque backdrop so the workspace behind it doesn't show through.
 */
export function StartGate({
  heading,
  practical,
  modeLabel,
  sections,
  notices,
  ackLabel,
  startLabel,
  starting,
  onStart,
  testId,
  startTestId,
}: {
  heading: string;
  practical: StudentPractical;
  modeLabel: ReactNode;
  sections: GateSection[];
  /** warnings / errors shown above the actions */
  notices?: ReactNode;
  ackLabel: string;
  startLabel: string;
  starting: boolean;
  onStart: () => void;
  testId: string;
  startTestId?: string;
}) {
  const [ack, setAck] = useState(false);
  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-canvas p-4 sm:items-center" data-testid={testId}>
      <div className="my-auto w-full max-w-xl animate-fade-in rounded-lg border border-line-strong bg-surface-1 text-fg">
        <div className="border-b border-line px-6 py-5">
          <h2 className="text-base font-semibold">{heading}</h2>
          <p className="mt-1 text-sm text-fg-muted">
            <span className="font-mono text-fg-faint">{practical.course_code}</span> · {practical.title}
          </p>
          <p className="mt-0.5 text-xs text-fg-faint">
            {practical.due_at ? `Due ${fmtDate(practical.due_at, true)}` : "No deadline"} · {modeLabel}
          </p>
        </div>

        <div className="space-y-5 px-6 py-5">
          {sections.map((s) => {
            const List = s.ordered ? "ol" : "ul";
            return (
              <section key={s.title}>
                <h3
                  className={cx(
                    "text-[11px] font-semibold uppercase tracking-wider",
                    s.tone === "fail" ? "text-rose-300" : "text-fg-faint",
                  )}
                >
                  {s.title}
                </h3>
                <List
                  className={cx(
                    "mt-2 space-y-1.5 pl-5 text-sm text-fg-muted marker:text-fg-faint",
                    s.ordered ? "list-decimal" : "list-disc",
                  )}
                >
                  {s.items.map((item, i) => (
                    <li key={i} className="pl-0.5">
                      {item}
                    </li>
                  ))}
                </List>
                {s.note && <p className="mt-2 text-sm text-fg">{s.note}</p>}
              </section>
            );
          })}
          {notices}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-4">
          <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-fg">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              className="h-4 w-4 cursor-pointer accent-indigo-500"
              data-testid="gate-ack"
            />
            {ackLabel}
          </label>
          <div className="ml-auto flex items-center gap-2">
            <Link href="/student" className="btn btn-ghost">
              Back
            </Link>
            <button
              onClick={onStart}
              disabled={!ack || starting}
              title={ack ? undefined : "Tick the box to confirm you have read the instructions"}
              className="btn btn-primary"
              data-testid={startTestId}
            >
              {starting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {startLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Wording shared by both gates, built from the lab's own numbers. */
export function submitRule(practical: StudentPractical): ReactNode {
  const hidden = practical.hidden_test_count;
  const worksheet = practical.lab_type === "worksheet";
  const noun = worksheet ? "check" : "test";
  return (
    <>
      <b className="font-medium text-fg">Submit</b> {worksheet ? "checks every answer" : "runs every test"}
      {hidden > 0 ? `, including ${hidden} hidden ${noun}${hidden === 1 ? "" : "s"},` : ""} and grades your work out of{" "}
      {practical.max_score}.
    </>
  );
}
