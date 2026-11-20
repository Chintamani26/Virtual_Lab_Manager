"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { DarkSkeleton, cx } from "@/components/ui";
import type { HintResponse } from "@/lib/types";

export const HINT_STEPS = [
  { level: 1, title: "Concept" },
  { level: 2, title: "Edge case" },
  { level: 3, title: "Logic" },
] as const;

function stepTitle(level: number) {
  return HINT_STEPS.find((s) => s.level === level)?.title ?? "Hint";
}

/** Three plain steps; the current one is marked with aria-current. */
function Stepper({ reached, current }: { reached: number; current: number }) {
  return (
    <ol className="grid grid-cols-3 gap-2" data-testid="hint-stepper">
      {HINT_STEPS.map((s) => {
        const active = s.level === current;
        const done = !active && (s.level < current || s.level <= reached);
        return (
          <li key={s.level} aria-current={active ? "step" : undefined} className="min-w-0">
            <span className={cx("block h-0.5 rounded-full", active ? "bg-brand-400" : done ? "bg-fg-faint" : "bg-line-strong")} />
            <span
              className={cx(
                "mt-1.5 block truncate text-[11px]",
                active ? "font-medium text-fg" : done ? "text-fg-muted" : "text-fg-faint",
              )}
            >
              Hint {s.level} · {s.title}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function HintCard({ h, compact = false, labels }: { h: HintResponse; compact?: boolean; labels?: Record<string, string> }) {
  const focus = h.focus_test ? (labels?.[h.focus_test] ?? h.focus_test) : null;
  const meta = [compact ? `Hint ${h.hint_level} · ${stepTitle(h.hint_level)}` : null, h.concept].filter(Boolean).join(" · ");
  return (
    <div className={cx("rounded-lg border border-line bg-surface-2", compact ? "p-3" : "p-4")}>
      {(meta || h.focus_test) && (
        <p className="flex flex-wrap items-baseline gap-x-2 text-xs text-fg-faint">
          {meta && <span>{meta}</span>}
          {focus && <span className={cx("text-rose-300/90", !labels?.[h.focus_test!] && "font-mono")}>{focus}</span>}
        </p>
      )}
      <Markdown dark className={meta || h.focus_test ? "mt-2" : undefined}>
        {h.hint}
      </Markdown>
      {h.guiding_question && <p className="mt-3 border-l-2 border-line-strong pl-3 text-sm text-fg">{h.guiding_question}</p>}
      <p className="mt-3 text-right text-[11px] text-fg-faint">
        {h.source === "gemini" ? "Gemini" : "Offline tutor"}
      </p>
    </div>
  );
}

/** Bottom drawer (tab 1): progressive hints in three levels; never reveals solution code. */
export function SocraticHintStepper({
  hints,
  loading,
  error,
  onAsk,
  hasFailingTests,
  hintsUsedBefore,
  disabled = false,
  labels,
}: {
  hints: HintResponse[];
  loading: boolean;
  error: string | null;
  onAsk: (question?: string) => void;
  hasFailingTests: boolean;
  hintsUsedBefore: number;
  /** exam locked / submitted: hints can't be requested */
  disabled?: boolean;
  /** worksheet labs: readable step names for the focus check (test name -> description) */
  labels?: Record<string, string>;
}) {
  const [question, setQuestion] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [hints.length]);

  const latest = hints[hints.length - 1];
  const sameTest = latest ? hints.filter((h) => h.focus_test === latest.focus_test) : [];
  const reached = sameTest.reduce((m, h) => Math.max(m, h.hint_level), 0);
  const current = latest ? latest.hint_level : 0;
  const earlier = hints.slice(0, -1).reverse();
  const atMax = latest ? latest.hint_level >= latest.max_hint_level : false;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (disabled) return;
    onAsk(question);
    setQuestion("");
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="tutor-panel">
      <div className="shrink-0 border-b border-line px-3 py-2.5">
        <Stepper reached={reached} current={current} />
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto scroll-dark px-3 py-3">
        {loading && (
          <div className="rounded-lg border border-line bg-surface-2 p-4" data-testid="hint-loading">
            <p className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Getting a hint…
            </p>
            <div className="mt-3 space-y-2" aria-hidden>
              <DarkSkeleton className="h-3 w-[92%]" />
              <DarkSkeleton className="h-3 w-[78%]" />
              <DarkSkeleton className="h-3 w-[64%]" />
            </div>
          </div>
        )}

        {!loading && latest && <HintCard key={hints.length} h={latest} labels={labels} />}

        {!loading && !latest && (
          <p className="text-sm text-fg-faint">
            {disabled
              ? "Hints are unavailable right now."
              : hasFailingTests
                ? labels
                  ? "Get a hint for a step that isn't right yet."
                  : "Get a hint for your failing test."
                : labels
                  ? "Check your answers first, then get a hint."
                  : "Run tests first, then get a hint."}
            {hintsUsedBefore > 0 && ` ${hintsUsedBefore} used earlier.`}
          </p>
        )}

        {error && <p className="rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p>}

        {earlier.length > 0 && (
          <details className="group rounded-lg border border-line">
            <summary className="flex h-8 cursor-pointer list-none items-center gap-1.5 px-2.5 text-xs text-fg-faint hover:text-fg-muted">
              <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
              Earlier hints ({earlier.length})
            </summary>
            <div className="space-y-2 p-2 pt-0">
              {earlier.map((h, i) => (
                <HintCard key={i} h={h} compact labels={labels} />
              ))}
            </div>
          </details>
        )}
      </div>

      <form onSubmit={submit} className="shrink-0 border-t border-line p-2.5">
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={disabled}
            placeholder="Question (optional)"
            aria-label="Question for the hint (optional)"
            className="h-8 min-w-0 flex-1 rounded-ctl bg-surface-2 px-3 text-sm text-fg outline-none ring-1 ring-inset ring-line-strong placeholder:text-fg-faint focus:ring-2 focus:ring-brand/60 disabled:opacity-50"
          />
          <button type="submit" disabled={loading || disabled} className="btn btn-secondary">
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {question.trim() ? "Ask" : !latest ? "Get a hint" : atMax ? "Ask again" : "Next hint"}
          </button>
        </div>
      </form>
    </div>
  );
}
