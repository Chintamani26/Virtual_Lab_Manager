"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { Markdown } from "./Markdown";
import { Button, Card, CardHeader, cx, inputCls } from "./ui";
import { api } from "@/lib/api";
import type { AskResponse } from "@/lib/types";

/** One question and its answer (or error). Newest first. */
type Turn = { question: string; res?: AskResponse; error?: string };

const SUGGESTIONS = [
  "Which lab has the lowest completion rate?",
  "Which students are at risk in CS201?",
  "What is the most common failing test?",
];

export function AnalyticsChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [turns.length]);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || loading) return;
    setTurns((t) => [{ question }, ...t]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.ask(question);
      setTurns((t) => t.map((x, i) => (i === 0 ? { ...x, res } : x)));
    } catch (e) {
      const error = e instanceof Error ? e.message : "Query failed";
      setTurns((t) => t.map((x, i) => (i === 0 ? { ...x, error } : x)));
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(input);
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader title="Ask a question" subtitle="Query courses, scores, and lab performance" />
      <div className="p-5">
        <form onSubmit={onSubmit} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Question"
            placeholder="Ask about completion, scores, or failing tests"
            className={cx(inputCls, "min-w-0 flex-1")}
          />
          <Button type="submit" disabled={loading || !input.trim()}>
            Ask
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => ask(s)}
              disabled={loading}
              className="rounded-md border border-slate-200 px-2.5 py-1 text-left text-xs text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {turns.length > 0 && (
        <div ref={scrollRef} className="divide-y divide-slate-100 border-t border-slate-100">
          {turns.map((t, i) => (
            <div key={turns.length - i} className="px-5 py-4">
              <p className="text-sm font-medium text-slate-900">{t.question}</p>
              {t.error ? (
                <p className="mt-2 text-sm text-rose-700">{t.error}</p>
              ) : !t.res ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading answer…
                </p>
              ) : (
                <Answer res={t.res} />
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Answer({ res }: { res: AskResponse }) {
  return (
    <div className="mt-2 text-slate-700">
      <Markdown>{res.answer}</Markdown>
      {res.highlights.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          {res.highlights.map((h, j) => (
            <li key={j}>{h}</li>
          ))}
        </ul>
      )}
      {res.table && res.table.rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr className="border-b border-slate-200">
                {res.table.columns.map((c) => (
                  <th key={c} className="whitespace-nowrap py-2 pr-4 font-medium last:pr-0">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {res.table.rows.map((r, ri) => (
                <tr key={ri} className="hover:bg-slate-50/60">
                  {r.map((cell, ci) => (
                    <td
                      key={ci}
                      className={cx("py-2 pr-4 text-slate-900 last:pr-0", typeof cell === "number" && "tabular-nums")}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-400">{res.source === "gemini" ? "Answered by Gemini" : "Offline analytics"}</p>
    </div>
  );
}
