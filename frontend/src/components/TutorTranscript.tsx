"use client";

import { useState } from "react";
import { Markdown } from "@/components/Markdown";
import { Card, CardHeader, cx } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import type { TutorMessage, Understanding } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const FLAG_LABELS: Record<string, string> = {
  injection: "Tried to override the tutor's rules",
  restricted: "Asked for restricted data",
  solution_request: "Asked for the solution",
  off_topic: "Off topic",
  code_removed: "Solution code removed",
  value_hidden: "Answer value hidden",
  leak_blocked: "Reply blocked",
};
const SKIP_FLAGS = new Set(["hidden_tests", "reference_solution", "other_students"]); // detail of "restricted"

const UNDERSTANDING: Record<Understanding, { label: string; cls: string }> = {
  understood: { label: "Understood", cls: "text-emerald-700" },
  partial: { label: "Partly", cls: "text-amber-700" },
  not_yet: { label: "Not yet", cls: "text-rose-700" },
};

const ACTION_LABELS: Record<string, string> = {
  explain_error: "Explain this error",
  explain_test: "Explain this test",
  explain_concept: "Explain the concept",
  next_hint: "Next hint",
  concept_check: "Concept check",
};

function Flags({ flags }: { flags: string[] }) {
  const shown = flags.filter((f) => !SKIP_FLAGS.has(f) && FLAG_LABELS[f]);
  if (shown.length === 0) return null;
  return <p className="mt-1 text-[11px] font-medium text-rose-700">{shown.map((f) => FLAG_LABELS[f]).join(" · ")}</p>;
}

function Message({ m }: { m: TutorMessage }) {
  if (m.role === "student") {
    return (
      <div className="flex flex-col items-end">
        <p className="ml-10 whitespace-pre-wrap break-words rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-800">
          {m.content}
        </p>
        <Flags flags={m.flags} />
      </div>
    );
  }
  const verdict = m.understanding ? UNDERSTANDING[m.understanding] : null;
  const meta = [
    m.hint_level ? `Hint level ${m.hint_level}` : ACTION_LABELS[m.action] ?? null,
    m.focus_test,
    m.source === "gemini" ? "Gemini" : m.source === "guard" ? "Tutor rules" : "Offline tutor",
  ].filter(Boolean);
  return (
    <div className="mr-10 rounded-lg border border-slate-200 px-3 py-2">
      <p className="mb-1 flex flex-wrap gap-x-2 text-[11px] text-slate-400">
        {verdict && <span className={cx("font-medium", verdict.cls)}>{verdict.label}</span>}
        <span>{meta.join(" · ")}</span>
      </p>
      <Markdown className="text-sm">{m.content}</Markdown>
      {m.guiding_question && <p className="mt-2 border-l-2 border-slate-200 pl-3 text-sm text-slate-700">{m.guiding_question}</p>}
      <Flags flags={m.flags} />
    </div>
  );
}

/** Faculty: the student's AI Lab Tutor conversation on this practical. */
export function TutorTranscriptCard({ submissionId }: { submissionId: string }) {
  const { data, error, loading } = useApi(() => api.submissionTutor(submissionId), [submissionId]);
  const [open, setOpen] = useState(false);

  let body;
  if (loading && !data) body = <p className="px-5 py-4 text-sm text-slate-500">Loading…</p>;
  else if (error || !data) body = <p className="px-5 py-4 text-sm text-slate-500">The tutor conversation couldn't be loaded.</p>;
  else if (data.messages.length === 0)
    body = <p className="px-5 py-4 text-sm text-slate-500">The student didn't use the AI tutor on this lab.</p>;
  else {
    const last = data.concept_checks[data.concept_checks.length - 1];
    const summary = [
      `${data.student_messages} message${data.student_messages === 1 ? "" : "s"} to the tutor`,
      data.hints > 0 ? `${data.hints} hint${data.hints === 1 ? "" : "s"} (up to level ${data.max_hint_level})` : "no hints",
    ];
    body = (
      <div className="px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm text-slate-600">
          <p>
            {summary.join(" · ")}
            {last && (
              <>
                {" · "}concept check: <span className={cx("font-medium", UNDERSTANDING[last].cls)}>{UNDERSTANDING[last].label}</span>
              </>
            )}
            {data.flagged > 0 && <span className="text-rose-700"> · {data.flagged} flagged</span>}
          </p>
          <button type="button" onClick={() => setOpen((o) => !o)} className="text-sm font-medium text-indigo-600 hover:text-indigo-800">
            {open ? "Hide conversation" : "Show conversation"}
          </button>
        </div>
        {open && (
          <div className="mt-4 max-h-[560px] space-y-3 overflow-auto pr-1" data-testid="tutor-transcript">
            {data.dropped > 0 && <p className="text-xs text-slate-400">{data.dropped} older messages are not shown.</p>}
            {data.messages.map((m) => (
              <div key={m.id}>
                <Message m={m} />
                <p className={cx("mt-0.5 text-[10px] text-slate-400", m.role === "student" && "text-right")}>
                  {fmtDate(m.created_at, true)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader title="AI tutor" subtitle="Guided help the student asked for on this lab" />
      {body}
    </Card>
  );
}
