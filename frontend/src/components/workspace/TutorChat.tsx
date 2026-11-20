"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { DarkSkeleton, cx } from "@/components/ui";
import type { TutorAction, TutorMessage, Understanding } from "@/lib/types";
import { HINT_STEPS } from "./SocraticHintStepper";

export type TestState = "none" | "failing" | "passing";

const ACTIONS: Record<Exclude<TutorAction, "chat">, string> = {
  explain_error: "Explain this error",
  explain_test: "Explain this test",
  explain_concept: "Explain the concept",
  next_hint: "Next hint",
  concept_check: "Check my understanding",
};

function actionsFor(state: TestState): Exclude<TutorAction, "chat">[] {
  return state === "passing"
    ? ["explain_concept", "explain_test", "concept_check"]
    : ["explain_error", "explain_test", "explain_concept", "next_hint"];
}

const UNDERSTANDING: Record<Understanding, { label: string; cls: string }> = {
  understood: { label: "Understood", cls: "text-emerald-300" },
  partial: { label: "Partly there", cls: "text-amber-300" },
  not_yet: { label: "Not yet", cls: "text-rose-300" },
};

function TutorBubble({ m, labels }: { m: TutorMessage; labels?: Record<string, string> }) {
  const step = m.hint_level ? HINT_STEPS.find((s) => s.level === m.hint_level) : undefined;
  const focus = m.focus_test ? (labels?.[m.focus_test] ?? m.focus_test) : null;
  const meta = [
    m.hint_level ? `Hint ${m.hint_level} of ${HINT_STEPS.length}${step ? ` · ${step.title}` : ""}` : null,
    m.expects_answer ? "Concept check" : null,
    m.concept,
  ].filter(Boolean);
  const verdict = m.understanding ? UNDERSTANDING[m.understanding] : null;
  return (
    <div className="mr-6 rounded-lg border border-line bg-surface-2 p-3" data-testid="tutor-message">
      {(meta.length > 0 || focus || verdict) && (
        <p className="mb-1.5 flex flex-wrap items-baseline gap-x-2 text-xs text-fg-faint">
          {verdict && <span className={cx("font-medium", verdict.cls)}>{verdict.label}</span>}
          {meta.length > 0 && <span>{meta.join(" · ")}</span>}
          {focus && <span className={cx("text-rose-300/90", !labels?.[m.focus_test!] && "font-mono")}>{focus}</span>}
        </p>
      )}
      <Markdown dark>{m.content}</Markdown>
      {m.guiding_question && (
        <p className="mt-2.5 border-l-2 border-line-strong pl-3 text-sm text-fg">{m.guiding_question}</p>
      )}
      <p className="mt-2 text-right text-[11px] text-fg-faint">
        {m.source === "gemini" ? "Gemini" : m.source === "guard" ? "Tutor rules" : "Offline tutor"}
      </p>
    </div>
  );
}

function StudentBubble({ text, pending = false }: { text: string; pending?: boolean }) {
  return (
    <div className="flex justify-end">
      <p
        className={cx(
          "ml-10 whitespace-pre-wrap break-words rounded-lg bg-surface-3 px-3 py-2 text-sm text-fg",
          pending && "opacity-70",
        )}
      >
        {text}
      </p>
    </div>
  );
}

/** Bottom drawer: the AI Lab Tutor. The conversation lives on the server; this only renders and sends. */
export function TutorChat({
  messages,
  pending,
  loading,
  error,
  onSend,
  testState,
  remaining,
  disabled = false,
  labels,
}: {
  messages: TutorMessage[];
  /** the student's message while the reply is on its way */
  pending: string | null;
  loading: boolean;
  error: string | null;
  onSend: (action: TutorAction, message?: string) => void;
  testState: TestState;
  remaining: number | null;
  /** exam locked / submitted: the tutor can't be used */
  disabled?: boolean;
  /** worksheet labs: readable step names (test name -> description) */
  labels?: Record<string, string>;
}) {
  const [text, setText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages.length, loading]);

  const last = messages[messages.length - 1];
  const answering = last?.role === "tutor" && last.expects_answer;
  const busy = loading || disabled;

  function send(action: TutorAction, withText = false) {
    if (busy) return;
    const msg = withText ? text.trim() : "";
    if (action === "chat" && !msg) return;
    onSend(action, msg || undefined);
    if (msg) setText("");
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send("chat", true);
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="tutor-panel">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto scroll-dark px-3 py-3">
        {messages.length === 0 && !pending && (
          <p className="text-sm text-fg-faint">
            {disabled
              ? "The tutor is unavailable right now."
              : "Ask about this lab, or pick an action below. The tutor guides you; it won't write the solution."}
          </p>
        )}

        {messages.map((m) =>
          m.role === "student" ? <StudentBubble key={m.id} text={m.content} /> : <TutorBubble key={m.id} m={m} labels={labels} />,
        )}

        {pending && <StudentBubble text={pending} pending />}

        {loading && (
          <div className="mr-6 rounded-lg border border-line bg-surface-2 p-3" data-testid="hint-loading">
            <p className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
            </p>
            <div className="mt-2.5 space-y-2" aria-hidden>
              <DarkSkeleton className="h-3 w-[90%]" />
              <DarkSkeleton className="h-3 w-[70%]" />
            </div>
          </div>
        )}

        {error && <p className="rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p>}
      </div>

      <div className="shrink-0 border-t border-line p-2.5">
        <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Quick actions">
          {actionsFor(testState).map((a) => (
            <button
              key={a}
              type="button"
              disabled={busy}
              onClick={() => send(a, a === "explain_concept")}
              title={a === "explain_concept" ? "Type a concept first to ask about it, or leave the box empty" : undefined}
              className="inline-flex h-7 items-center rounded-ctl bg-surface-2 px-2.5 text-xs text-fg-muted ring-1 ring-inset ring-line-strong transition hover:bg-surface-3 hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
              data-testid={`tutor-action-${a}`}
            >
              {ACTIONS[a]}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={disabled}
            maxLength={1000}
            placeholder={answering ? "Answer the concept check in your own words…" : "Ask a question about your lab…"}
            aria-label="Message to the tutor"
            className="h-8 min-w-0 flex-1 rounded-ctl bg-surface-2 px-3 text-sm text-fg outline-none ring-1 ring-inset ring-line-strong placeholder:text-fg-faint focus:ring-2 focus:ring-brand/60 disabled:opacity-50"
          />
          <button type="submit" disabled={busy || !text.trim()} className="btn btn-secondary">
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Send
          </button>
        </form>
        {remaining !== null && remaining <= 10 && (
          <p className="mt-1.5 text-[11px] text-fg-faint">{remaining} tutor questions left today for this lab.</p>
        )}
      </div>
    </div>
  );
}
