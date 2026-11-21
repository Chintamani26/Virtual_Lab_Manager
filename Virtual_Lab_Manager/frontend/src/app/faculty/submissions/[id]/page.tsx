"use client";

import { useEffect, useState, type FormEvent } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { PageContainer } from "@/components/AppShell";
import { IntegrityBadge, IntegrityCard } from "@/components/integrity";
import { Markdown } from "@/components/Markdown";
import { RubricBreakdown, TestResultsList } from "@/components/review";
import { TutorTranscriptCard } from "@/components/TutorTranscript";
import {
  Button,
  Card,
  ErrorState,
  Field,
  InlineError,
  PageHeader,
  PageSkeleton,
  StatusBadge,
  cx,
  inputCls,
  underlineTabCls,
} from "@/components/ui";
import { NotebookEditor } from "@/components/workspace/NotebookEditor";
import { WorksheetAnswers } from "@/components/WorksheetAnswers";
import { languageForFile } from "@/components/workspace/CodeEditor";
import { api, fmtDate, fmtScore } from "@/lib/api";
import type { Submission } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const CodeEditor = dynamic(() => import("@/components/workspace/CodeEditor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-400">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading editor…
    </div>
  ),
});

export default function SubmissionReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload, setData } = useApi(() => api.getSubmission(id), [id]);

  if (loading && !data)
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  if (error || !data)
    return (
      <PageContainer>
        <ErrorState message={error ?? "Submission not found"} onRetry={reload} />
      </PageContainer>
    );

  return <Review submission={data} onUpdated={setData} />;
}

function Review({ submission: s, onUpdated }: { submission: Submission; onUpdated: (s: Submission) => void }) {
  const fileNames = Object.keys(s.files);
  const [activeFile, setActiveFile] = useState(fileNames[0] ?? "");
  const [evalTab, setEvalTab] = useState<"rubric" | "tests">("rubric");
  const [score, setScore] = useState<string>(s.faculty_score !== null ? String(s.faculty_score) : "");
  const [comment, setComment] = useState(s.faculty_comment ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // worksheet submissions are shown as a readings table + step answers, which needs the lab's worksheet layout
  const { data: practical } = useApi(
    () => (s.lab_type === "worksheet" ? api.getPractical(s.practical_id) : Promise.resolve(null)),
    [s.practical_id, s.lab_type],
  );

  useEffect(() => {
    setScore(s.faculty_score !== null ? String(s.faculty_score) : "");
    setComment(s.faculty_comment ?? "");
  }, [s.faculty_score, s.faculty_comment]);

  async function submitReview(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaved(false);
    let fs: number | null = null;
    if (score.trim() !== "") {
      fs = Number(score);
      if (Number.isNaN(fs) || fs < 0 || fs > s.max_score) {
        setErr(`Score must be between 0 and ${s.max_score}.`);
        return;
      }
    }
    setSaving(true);
    try {
      const updated = await api.reviewSubmission(s.id, { faculty_score: fs, faculty_comment: comment.trim() || null });
      onUpdated(updated);
      setSaved(true);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Review failed");
    } finally {
      setSaving(false);
    }
  }

  const finalScore = s.final_score ?? s.rubric_score;
  const failedTests = s.tests_total - s.tests_passed;

  return (
    <PageContainer>
      <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
        <Link href="/faculty" className="hover:text-slate-900">
          Dashboard
        </Link>
        <span aria-hidden>/</span>
        <Link href={`/faculty/practicals/${s.practical_id}/submissions`} className="hover:text-slate-900">
          {s.practical_title}
        </Link>
        <span aria-hidden>/</span>
        <span className="text-slate-700">{s.student_name}</span>
      </nav>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{s.student_name}</span>
            <span className="flex items-center gap-2">
              <StatusBadge status={s.status} />
              <IntegrityBadge integrity={s.integrity ?? null} />
            </span>
          </span>
        }
        subtitle={
          <>
            {s.roll_number && <span className="font-mono">{s.roll_number}</span>}
            {s.roll_number && " · "}
            {s.course_code} · Submitted {fmtDate(s.submitted_at, true)}
          </>
        }
      />

      <div className="grid items-start gap-6 xl:grid-cols-[1.45fr_1fr]">
        <div className="min-w-0 space-y-6">
          {/* Code viewer */}
          <Card className="overflow-hidden">
            <div className="flex items-center gap-1 border-b border-slate-100 px-3 pt-2">
              {fileNames.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setActiveFile(f)}
                  className={cx(
                    "-mb-px border-b-2 px-3 py-1.5 font-mono text-xs transition-colors",
                    activeFile === f
                      ? "border-indigo-600 font-medium text-slate-900"
                      : "border-transparent text-slate-500 hover:text-slate-800",
                  )}
                >
                  {f === "answers.json" ? "Worksheet" : f}
                </button>
              ))}
              <span className="ml-auto pb-1.5 text-xs text-slate-400">Read-only</span>
            </div>
            <div className="h-[520px]">
              {s.lab_type === "worksheet" && practical?.worksheet ? (
                <WorksheetAnswers spec={practical.worksheet} value={s.files[activeFile] ?? ""} results={s.test_results} />
              ) : activeFile.endsWith(".ipynb") ? (
                <NotebookEditor value={s.files[activeFile] ?? ""} readOnly dark={false} />
              ) : (
                <CodeEditor
                  path={`review/${s.id}/${activeFile}`}
                  value={s.files[activeFile] ?? ""}
                  language={languageForFile(activeFile)}
                  theme="light"
                  readOnly
                />
              )}
            </div>
          </Card>

          {/* Combined evaluation card */}
          <Card>
            <div className="flex items-center gap-6 border-b border-slate-100 px-5 pt-3">
              <button type="button" onClick={() => setEvalTab("rubric")} className={underlineTabCls(evalTab === "rubric")}>
                Rubric
              </button>
              <button type="button" onClick={() => setEvalTab("tests")} className={underlineTabCls(evalTab === "tests")}>
                <span>Tests</span>
                <span
                  className={cx(
                    "text-xs tabular-nums",
                    failedTests > 0 ? "text-rose-600" : "text-slate-400",
                  )}
                >
                  {s.tests_passed}/{s.tests_total}
                </span>
              </button>
            </div>

            {evalTab === "rubric" ? (
              <>
                <RubricBreakdown items={s.rubric_breakdown} />
                {s.ai_feedback && (
                  <div className="border-t border-slate-100 px-5 py-4">
                    <p className="mb-2 text-xs font-medium text-slate-500">AI summary</p>
                    <Markdown>{s.ai_feedback}</Markdown>
                  </div>
                )}
              </>
            ) : (
              <TestResultsList tests={s.test_results} />
            )}
          </Card>

          <TutorTranscriptCard submissionId={s.id} />
        </div>

        {/* Grading & Integrity sidebar */}
        <div className="space-y-6 xl:sticky xl:top-20">
          <Card className="p-5">
            <div className="flex items-baseline justify-between gap-4">
              <div>
                <p className="text-xs font-medium text-slate-500">Final score</p>
                <p className="mt-1 text-3xl font-semibold tabular-nums text-slate-900">
                  {fmtScore(finalScore)}
                  <span className="text-lg font-normal text-slate-400">/{s.max_score}</span>
                </p>
              </div>
              <div className="text-right text-xs text-slate-500">
                <p className="tabular-nums">
                  AI {fmtScore(s.rubric_score, s.max_score)} · {s.tests_passed}/{s.tests_total} tests
                </p>
                {s.grading_model && <p className="mt-0.5 font-mono text-[11px] text-slate-400">{s.grading_model}</p>}
              </div>
            </div>

            <form onSubmit={submitReview} className="mt-5 space-y-4 border-t border-slate-100 pt-4">
              <Field label={`Override score (0–${s.max_score})`} hint="Leave blank to keep the AI score.">
                <input
                  type="number"
                  step={0.5}
                  min={0}
                  max={s.max_score}
                  className={inputCls}
                  value={score}
                  placeholder={s.rubric_score !== null ? String(s.rubric_score) : ""}
                  onChange={(e) => setScore(e.target.value)}
                />
              </Field>
              <Field label="Comment to student">
                <textarea
                  className={cx(inputCls, "min-h-20")}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Optional feedback"
                />
              </Field>
              <InlineError message={err} />
              <div className="flex items-center gap-3">
                <Button type="submit" loading={saving}>
                  {s.status === "reviewed" ? "Update review" : "Approve and save"}
                </Button>
                {saved && (
                  <span className="text-xs text-emerald-700">
                    Saved{s.reviewed_at ? ` · ${fmtDate(s.reviewed_at, true)}` : ""}
                  </span>
                )}
              </div>
            </form>
          </Card>

          <IntegrityCard submissionId={s.id} integrity={s.integrity ?? null} />
        </div>
      </div>
    </PageContainer>
  );
}
