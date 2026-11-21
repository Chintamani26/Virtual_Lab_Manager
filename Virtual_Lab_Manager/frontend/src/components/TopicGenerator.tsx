"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, CardHeader, Field, InlineError, SegmentedControl, inputCls } from "./ui";
import { api } from "@/lib/api";
import type { Difficulty, GeneratedPractical } from "@/lib/types";

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
] as const;

/** Faculty: generate a whole coding practical from a topic. The result fills the form as an unsaved draft. */
export function TopicGenerator({ courseId, onGenerated }: { courseId: string; onGenerated: (g: GeneratedPractical) => void }) {
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("intermediate");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GeneratedPractical | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("topic");
    if (t) setTopic(t);
  }, []);

  async function generate(e: FormEvent) {
    e.preventDefault();
    if (topic.trim().length < 3) return setError("Enter a topic of at least 3 characters.");
    setLoading(true);
    setError(null);
    try {
      const g = await api.generatePractical({
        topic: topic.trim(), difficulty, course_id: courseId || undefined, notes: notes.trim() || undefined,
      });
      setResult(g);
      onGenerated(g);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function copyReference() {
    try {
      await navigator.clipboard.writeText(result?.reference_files["main.py"] ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy to clipboard. Copy the code manually instead.");
    }
  }

  const v = result?.verification;
  return (
    <Card>
      <CardHeader title="Create from a topic" subtitle="Gemini drafts the brief, starter code, tests, rubric and viva questions. Coding labs." />
      <form onSubmit={generate} className="grid gap-4 p-5 md:grid-cols-[1fr_auto]">
        <Field label="Topic">
          <input className={inputCls} value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={200}
            placeholder="e.g. Stack implementation using a linked list" data-testid="topic-input" />
        </Field>
        <div>
          <span className="mb-1.5 block text-sm font-medium text-slate-700">Difficulty</span>
          <SegmentedControl options={LEVELS} value={difficulty} onChange={setDifficulty} ariaLabel="Difficulty" />
        </div>
        <div className="md:col-span-2">
          <Field label="Notes (optional)">
            <input className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000}
              placeholder="e.g. must use recursion; no built-in sort" />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <Button type="submit" loading={loading} data-testid="topic-generate">
            {result ? "Generate again" : "Generate practical"}
          </Button>
          {loading && <span className="text-sm text-slate-500">Writing the lab and checking its tests in the sandbox…</span>}
        </div>
        <div className="md:col-span-2">
          <InlineError message={error} />
        </div>
      </form>

      {result && v && (
        <div className="space-y-3 border-t border-slate-100 px-5 py-4 text-sm" data-testid="topic-result">
          <p className={v.verified ? "text-emerald-700" : "text-amber-700"}>
            {v.verified ? "Verified in the sandbox: " : "Check the tests: "}
            {v.reference_passed} of {v.tests_total} tests pass on the reference solution and {v.starter_failed} fail on
            the starter code.
            {v.dropped.length > 0 && ` Removed ${v.dropped.length} test${v.dropped.length === 1 ? "" : "s"} that didn't check the right thing.`}
          </p>
          {v.note && <p className="text-amber-700">{v.note}</p>}
          <p className="text-slate-600">
            The form below now holds &ldquo;{result.title}&rdquo; as an unsaved draft. Review each tab, then save. Nothing has been
            published.
          </p>
          <details className="rounded-md border border-slate-200">
            <summary className="cursor-pointer px-3 py-2 text-slate-700">Reference solution (for you only, never shown to students)</summary>
            <div className="border-t border-slate-100 p-3">
              <pre className="max-h-72 overflow-auto rounded bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-100">
                {result.reference_files["main.py"]}
              </pre>
              <div className="mt-2 flex items-center gap-3">
                <Button type="button" size="sm" variant="secondary" onClick={copyReference}>
                  {copied ? "Copied" : "Copy"}
                </Button>
                <span className="text-xs text-slate-500">After saving the draft, paste it into Validate on the Code tab.</span>
              </div>
            </div>
          </details>
          <p className="text-xs text-slate-400">Gemini · {result.model}</p>
        </div>
      )}
    </Card>
  );
}
