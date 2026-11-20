"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { DarkSkeleton, cx } from "@/components/ui";
import { CircuitWorkbench } from "@/components/workspace/CircuitWorkbench";
import { InstructionsView } from "@/components/workspace/InstructionsView";
import { LabHeader } from "@/components/workspace/LabHeader";
import { MultiTabEditor } from "@/components/workspace/MultiTabEditor";
import { NotebookEditor } from "@/components/workspace/NotebookEditor";
import { ExamGate, ExamLockOverlay, SebRequiredGate } from "@/components/workspace/ExamLockdown";
import { FloatingNotice, ProctorGate } from "@/components/workspace/Proctoring";
import {
  ConfirmSubmitDialog,
  RubricPanel,
  RubricScorecardModal,
  SubmittedBanner,
} from "@/components/workspace/RubricScorecard";
import { TutorChat } from "@/components/workspace/TutorChat";
import { TestRunnerTerminal } from "@/components/workspace/TestRunnerTerminal";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { WorksheetView } from "@/components/workspace/worksheet/WorksheetView";
import { BreakDialog, BreakOverlay, type BreakRules } from "@/components/workspace/Break";
import { languageForFile } from "@/components/workspace/CodeEditor";
import type { EditorHandle, MobilePane, RunKind, SaveState } from "@/components/workspace/types";
import { api, fmtScore } from "@/lib/api";
import type { ExecutionResult, LintResponse, StudentPractical, Submission, TutorAction, TutorMessage } from "@/lib/types";
import { useExamLockdown } from "@/lib/useExamLockdown";
import { useProctoring } from "@/lib/useProctoring";

const CodeEditor = dynamic(() => import("@/components/workspace/CodeEditor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center gap-2 bg-surface-1 text-sm text-fg-faint">
      <Loader2 className="h-4 w-4 animate-spin" /> Loading editor…
    </div>
  ),
});

function submissionAsResult(s: Submission): ExecutionResult {
  return {
    execution_id: null,
    engine: "submission",
    lab_type: s.lab_type,
    mode: "test",
    status: "ok",
    stdout: "",
    stderr: "",
    tests: s.test_results,
    tests_passed: s.tests_passed,
    tests_total: s.tests_total,
    duration_ms: 0,
    cell_outputs: null,
    truth_table: null,
    summary: `${s.tests_passed}/${s.tests_total} passed, incl. hidden`,
  };
}

const isNarrow = () => typeof window !== "undefined" && !window.matchMedia("(min-width: 1024px)").matches;

export default function LabWorkspacePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [practical, setPractical] = useState<StudentPractical | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [files, setFiles] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<string>("instructions");
  const [mobilePane, setMobilePane] = useState<MobilePane>("editor");

  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [resultSnapshot, setResultSnapshot] = useState<string | null>(null);
  const [running, setRunning] = useState<RunKind | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // AI Lab Tutor: the conversation is stored server-side and loaded with the lab
  const [tutorMessages, setTutorMessages] = useState<TutorMessage[]>([]);
  const [tutorPending, setTutorPending] = useState<string | null>(null);
  const [tutorLoading, setTutorLoading] = useState(false);
  const [tutorError, setTutorError] = useState<string | null>(null);
  const [tutorRemaining, setTutorRemaining] = useState<number | null>(null);

  const [submission, setSubmission] = useState<Submission | null>(null);
  const [lowerTab, setLowerTab] = useState<"tutor" | "rubric">("tutor");
  const [scorecard, setScorecard] = useState<{ open: boolean; loading: boolean }>({ open: false, loading: false });
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [breakDialog, setBreakDialog] = useState(false);
  /** proctored lab that was handed in: read-only and not recorded until Keep working opens a new session */
  const [reviewing, setReviewing] = useState(false);

  const [lint, setLint] = useState<Record<string, LintResponse>>({});
  const [lintLoading, setLintLoading] = useState(false);

  const [save, setSave] = useState<SaveState>({ state: "clean", at: null });

  const filesRef = useRef(files);
  filesRef.current = files;
  const versionRef = useRef(0);
  const savedVersionRef = useRef(0);
  const lastTestedRef = useRef<string | null>(null);
  const lintSeqRef = useRef(0);
  const editorHandleRef = useRef<EditorHandle | null>(null);

  // ---------- proctoring (v1.1) — older backends omit `proctored`: default to proctored ----------
  const proctored = practical ? (practical.proctored ?? true) : false;
  const proctoring = useProctoring(id, proctored, practical?.proctoring_summary);
  const proctoringRef = useRef(proctoring);
  proctoringRef.current = proctoring;

  // ---------- exam lockdown (v1.2) — one tab, lock on leaving, mentor unlock ----------
  const exam = useExamLockdown({
    practicalId: id,
    lockdownMode: practical?.lockdown_mode,
    initial: practical?.exam,
    proctoring,
  });
  const examRef = useRef(exam);
  examRef.current = exam;
  /** lockdown lab that this tab can't work on right now (gate, locked, elsewhere, submitted…) */
  const examBlocked = exam.enabled && exam.phase !== "live";
  const examBlockedRef = useRef(examBlocked);
  examBlockedRef.current = examBlocked;
  /** nothing can be edited or run right now: exam not live, or a proctored lab was handed in */
  const blocked = examBlocked || reviewing;
  const blockedRef = useRef(blocked);
  blockedRef.current = blocked;

  // ---------- load ----------
  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const p = await api.studentPractical(id);
      setPractical(p);
      const hasDraft = !!p.draft_files && Object.keys(p.draft_files).length > 0;
      const sub = p.latest_submission;
      // no draft but already submitted: continue from the submission and show its results
      const fromSubmission = !hasDraft && !!sub && Object.keys(sub.files).length > 0;
      const initial = hasDraft ? p.draft_files! : fromSubmission ? sub!.files : p.starter_files;
      setFiles(initial);
      setSubmission(sub);
      // already handed in: show the results without opening a proctored session (exams use their own phase)
      setReviewing(!!sub && (p.proctored ?? true) && (p.lockdown_mode ?? "off") === "off");
      if (fromSubmission) {
        setResult(submissionAsResult(sub!));
        setResultSnapshot(JSON.stringify(initial));
      }
      setSave({ state: "clean", at: p.draft_updated_at });
      setActiveTab(hasDraft || fromSubmission ? Object.keys(initial)[0] ?? "instructions" : "instructions");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load lab");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let live = true;
    api
      .tutorHistory(id)
      .then((t) => {
        if (!live) return;
        setTutorMessages(t.messages);
        setTutorRemaining(t.remaining_today);
      })
      .catch(() => {}); // history is a convenience: the tutor still works without it
    return () => {
      live = false;
    };
  }, [id]);

  // ---------- autosave (debounced 2s) ----------
  const saveNow = useCallback(async () => {
    if (!practical) return;
    if (examBlockedRef.current) return; // the server refuses drafts while the exam is locked / not started
    if (versionRef.current === savedVersionRef.current) return;
    const version = versionRef.current;
    setSave((s) => ({ ...s, state: "saving" }));
    try {
      const res = await api.saveDraft(id, filesRef.current);
      savedVersionRef.current = version;
      setSave({ state: versionRef.current === version ? "saved" : "dirty", at: res.saved_at });
    } catch (e) {
      if (examRef.current.handleError(e)) setSave((s) => ({ ...s, state: "dirty" }));
      else setSave((s) => ({ ...s, state: "error" }));
    }
  }, [id, practical]);

  // back in the exam (start / resume): save anything typed just before a lock
  useEffect(() => {
    if (exam.phase === "live" && versionRef.current !== savedVersionRef.current) void saveNow();
  }, [exam.phase, saveNow]);

  useEffect(() => {
    if (versionRef.current === 0) return;
    const t = setTimeout(() => void saveNow(), 2000);
    return () => clearTimeout(t);
  }, [files, saveNow]);

  function updateFile(name: string, content: string) {
    versionRef.current += 1;
    setSave((s) => ({ ...s, state: "dirty" }));
    setFiles((f) => ({ ...f, [name]: content }));
  }

  // ---------- lint (debounced 1.5s on the active file) ----------
  const activeContent = activeTab !== "instructions" ? files[activeTab] : undefined;
  useEffect(() => {
    if (!practical || activeTab === "instructions" || activeContent === undefined) return;
    if (blocked || practical.lab_type === "worksheet") return; // worksheets are values, not code
    const filename = activeTab;
    const t = setTimeout(async () => {
      const seq = ++lintSeqRef.current;
      setLintLoading(true);
      try {
        const res = await api.lint(id, filesRef.current, filename);
        if (seq === lintSeqRef.current) setLint((l) => ({ ...l, [filename]: res }));
      } catch {
        /* lint is best-effort */
      } finally {
        if (seq === lintSeqRef.current) setLintLoading(false);
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [activeContent, activeTab, id, practical, blocked]);

  // ---------- actions ----------
  const runCode = useCallback(
    async (mode: "run" | "test") => {
      if (running || blockedRef.current || proctoringRef.current.paused) return;
      setRunning(mode);
      setActionError(null);
      try {
        const snapshot = filesRef.current;
        const res = await api.run(id, snapshot, mode);
        setResult(res);
        setResultSnapshot(JSON.stringify(snapshot));
        if (mode === "test") lastTestedRef.current = JSON.stringify(snapshot);
        if (isNarrow()) setMobilePane("results");
      } catch (e) {
        if (!examRef.current.handleError(e)) setActionError(e instanceof Error ? e.message : "Execution failed");
      } finally {
        setRunning(null);
      }
    },
    [id, running],
  );

  const askTutor = useCallback(
    async (action: TutorAction, message?: string) => {
      if (blockedRef.current) return;
      setLowerTab("tutor");
      setTutorError(null);
      setTutorLoading(true);
      setTutorPending(message?.trim() || null);
      if (isNarrow()) setMobilePane("results");
      try {
        // The tutor reads the latest server-side test run — refresh it if the code changed.
        const snapshot = JSON.stringify(filesRef.current);
        if (lastTestedRef.current !== snapshot) {
          setRunning("test");
          try {
            const res = await api.run(id, filesRef.current, "test");
            setResult(res);
            setResultSnapshot(snapshot);
            lastTestedRef.current = snapshot;
          } finally {
            setRunning(null);
          }
        }
        const reply = await api.tutor(id, action, message);
        setTutorMessages((prev) => [...prev, ...reply.messages]);
        setTutorRemaining(reply.remaining_today);
      } catch (e) {
        if (!examRef.current.handleError(e)) setTutorError(e instanceof Error ? e.message : "The tutor is unavailable right now");
      } finally {
        setTutorPending(null);
        setTutorLoading(false);
      }
    },
    [id],
  );

  const requestSubmit = useCallback(() => {
    if (!running && !blockedRef.current && !proctoringRef.current.paused) setConfirmOpen(true);
  }, [running]);

  // ---------- Pause: a declared break (exam: limited by the server; proctored lab: recorded) ----------
  const startBreak = useCallback(async () => {
    setBreakDialog(false);
    await saveNow(); // the server refuses drafts during an exam break
    await proctoringRef.current.flush();
    if (examRef.current.enabled) await examRef.current.pause();
    else proctoringRef.current.pause({ record: true });
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
  }, [saveNow]);

  const submit = useCallback(async () => {
    if (running || blockedRef.current) return;
    setConfirmOpen(false);
    setRunning("submit");
    setActionError(null);
    setScorecard({ open: true, loading: true });
    const recording = proctoringRef.current.started;
    // The work is handed in from here: leaving the tab or fullscreen while it is graded
    // (or afterwards) is no longer counted, and doesn't lock an exam.
    examRef.current.setHandingIn(true);
    try {
      void saveNow();
      // sends every proctoring event + final typing stats before grading, then stops recording
      await proctoringRef.current.end();
      const s = await api.submit(id, filesRef.current);
      setSubmission(s);
      setResult(submissionAsResult(s));
      setResultSnapshot(JSON.stringify(filesRef.current));
      setPractical((p) => (p ? { ...p, latest_submission: s, submissions_used: (p.submissions_used ?? 0) + 1 } : p));
      if (examRef.current.enabled) examRef.current.markSubmitted(); // the exam ends; workspace becomes read-only
      else if (proctoringRef.current.enabled) setReviewing(true); // read-only until Keep working
      if (recording && document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
      setScorecard({ open: true, loading: false });
    } catch (e) {
      setScorecard({ open: false, loading: false });
      if (recording) void proctoringRef.current.start(); // nothing was handed in: keep recording
      if (!examRef.current.handleError(e)) setActionError(e instanceof Error ? e.message : "Submission failed");
    } finally {
      examRef.current.setHandingIn(false);
      setRunning(null);
    }
  }, [id, running, saveNow]);

  /** proctored lab, after submitting: back to editing through the start screen (a new proctored session) */
  const keepWorking = useCallback(() => {
    setScorecard({ open: false, loading: false });
    setReviewing(false);
  }, []);

  const viewBreakdown = useCallback(() => {
    setScorecard({ open: false, loading: false });
    setLowerTab("rubric");
    if (isNarrow()) setMobilePane("results");
  }, []);

  // Switching role / logging out mid-exam leaves the exam: record it with the student's token first.
  // ---------- keyboard shortcuts (capture phase so Monaco doesn't swallow them) ----------
  const runRef = useRef(runCode);
  runRef.current = runCode;
  const saveRef = useRef(saveNow);
  saveRef.current = saveNow;
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        void runRef.current("test");
      } else if (e.key.toLowerCase() === "s") {
        e.preventDefault();
        e.stopPropagation();
        void saveRef.current();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  // ---------- render ----------
  if (loadError) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-canvas text-sm text-fg-muted">
        <p>{loadError}</p>
        <div className="flex gap-2">
          <button onClick={load} className="btn btn-secondary">
            Retry
          </button>
          <Link href="/student" className="btn btn-primary">
            Back to labs
          </Link>
        </div>
      </div>
    );
  }

  if (!practical) return <WorkspaceSkeleton />;

  const fileNames = Object.keys(files);
  const worksheet = practical.lab_type === "worksheet" && practical.worksheet ? practical.worksheet : null;
  const hasFailing = !!result && result.mode === "test" && result.tests_passed < result.tests_total;
  const visibleTests = practical.test_cases.filter((t) => !t.hidden).length;
  const isCircuitTab = activeTab.endsWith(".sim");
  const stale = resultSnapshot !== null && resultSnapshot !== JSON.stringify(files);
  const finalScore = submission ? (submission.final_score ?? submission.rubric_score) : null;
  const breakRules: BreakRules = {
    exam: exam.enabled,
    left: exam.breaksLeft,
    max: exam.state?.max_breaks ?? 0,
    limitS: exam.state?.break_limit_s ?? 600,
  };
  const canPause = proctored && (exam.enabled ? exam.phase === "live" : proctoring.started && !proctoring.paused);
  const onExamBreak = exam.enabled && exam.phase === "paused" && !!exam.state;
  const limit = practical.submission_limit;
  const canKeepWorking = !limit || (practical.submissions_used ?? 0) < limit;

  const editor = (
    <CodeEditor
      path={`${practical.id}/${activeTab}`}
      value={files[activeTab] ?? ""}
      onChange={(v) => updateFile(activeTab, v)}
      language={languageForFile(activeTab)}
      diagnostics={activeTab !== "instructions" ? lint[activeTab]?.diagnostics : undefined}
      proctoring={proctored ? proctoring : undefined}
      onReady={(h) => (editorHandleRef.current = h)}
      readOnly={blocked}
    />
  );

  return (
    <>
      <WorkspaceShell
        mobilePane={mobilePane}
        onMobilePaneChange={setMobilePane}
        resultsBadge={
          result && result.mode === "test" ? (
            <span className={cx("font-mono text-[11px]", hasFailing ? "text-amber-300" : "text-emerald-300")}>
              {result.tests_passed}/{result.tests_total}
            </span>
          ) : null
        }
        header={
          <LabHeader
            practical={practical}
            result={result}
            running={running}
            hintLoading={tutorLoading}
            save={save}
            proctored={proctored}
            proctorSummary={proctoring.summary}
            onRun={() => void runCode("run")}
            onRunTests={() => void runCode("test")}
            onAskTutor={() => void askTutor("next_hint")}
            onSubmit={requestSubmit}
            exam={exam.enabled ? { mode: exam.mode, violations: exam.state?.violations ?? 0 } : null}
            actionsDisabled={blocked}
            lockNav={exam.phase === "live"}
            onPause={canPause ? () => setBreakDialog(true) : undefined}
            pauseBlocked={exam.enabled && exam.breaksLeft === 0 ? "You have used all your breaks for this exam" : null}
          />
        }
        left={
          <MultiTabEditor
            files={fileNames}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            lintByFile={lint}
            lintLoading={lintLoading}
            onJump={(line, col) => editorHandleRef.current?.reveal(line, col)}
            engine={result?.engine}
          >
            {activeTab === "instructions" ? (
              <InstructionsView practical={practical} />
            ) : worksheet && activeTab === "answers.json" ? (
              <WorksheetView
                spec={worksheet}
                value={files["answers.json"] ?? ""}
                onChange={(v) => updateFile("answers.json", v)}
                result={result}
                checkedValue={resultSnapshot ? (JSON.parse(resultSnapshot)["answers.json"] ?? null) : null}
                running={running !== null}
                onCheck={() => void runCode("test")}
                readOnly={blocked}
                typing={proctored ? proctoring : undefined}
              />
            ) : activeTab.endsWith(".ipynb") ? (
              <NotebookEditor
                value={files[activeTab] ?? ""}
                onChange={(v) => updateFile(activeTab, v)}
                cellOutputs={result?.cell_outputs}
                onRunAll={() => void runCode("run")}
                typing={proctored ? proctoring : undefined}
                readOnly={blocked}
              />
            ) : isCircuitTab ? (
              <div className="grid h-full grid-rows-[minmax(0,1fr)_minmax(0,1.05fr)]">
                <div className="min-h-0">{editor}</div>
                <div className="min-h-0 border-t border-line bg-canvas/40">
                  <CircuitWorkbench
                    result={result && result.lab_type === "circuit" ? result : null}
                    specs={practical.test_cases}
                    stale={stale}
                    running={running !== null}
                    onSimulate={() => void runCode("test")}
                  />
                </div>
              </div>
            ) : (
              editor
            )}
          </MultiTabEditor>
        }
        right={
          <div className="grid h-full min-h-0 grid-rows-[minmax(0,1.05fr)_minmax(0,1fr)]">
            <div className="min-h-0 border-b border-line">
              <TestRunnerTerminal
                result={result}
                running={running}
                labType={practical.lab_type}
                labels={worksheet ? Object.fromEntries(practical.test_cases.map((t) => [t.name, t.description])) : undefined}
                expectedCount={result?.tests_total ?? visibleTests}
                submitted={exam.phase === "submitted" || reviewing}
              />
            </div>
            <div className="flex min-h-0 flex-col">
              <div className="flex h-10 shrink-0 items-stretch border-b border-line bg-surface-1" role="tablist">
                <DrawerTab active={lowerTab === "tutor"} onClick={() => setLowerTab("tutor")} testId="drawer-tutor">
                  Tutor
                </DrawerTab>
                <DrawerTab active={lowerTab === "rubric"} onClick={() => setLowerTab("rubric")} testId="drawer-rubric">
                  Rubric
                  {submission && (
                    <span className="font-mono text-[11px] text-fg-faint">
                      {fmtScore(finalScore)}/{submission.max_score}
                    </span>
                  )}
                </DrawerTab>
              </div>
              <div className="min-h-0 flex-1">
                {lowerTab === "tutor" ? (
                  <TutorChat
                    messages={tutorMessages}
                    pending={tutorPending}
                    loading={tutorLoading}
                    error={tutorError}
                    onSend={(action, message) => void askTutor(action, message)}
                    testState={!result || result.mode !== "test" ? "none" : hasFailing ? "failing" : "passing"}
                    remaining={tutorRemaining}
                    disabled={blocked}
                    labels={worksheet ? Object.fromEntries(practical.test_cases.map((t) => [t.name, t.description])) : undefined}
                  />
                ) : (
                  <RubricPanel submission={submission} />
                )}
              </div>
            </div>
          </div>
        }
        overlays={
          <div className="pointer-events-none absolute inset-x-0 top-3 z-50 flex flex-col items-center gap-2 px-4">
            {proctored && !exam.enabled && proctoring.started && proctoring.fullscreenLost && (
              <FloatingNotice
                tone="warn"
                action={
                  <button
                    onClick={proctoring.returnToFullscreen}
                    className="ml-1 inline-flex h-7 shrink-0 items-center rounded-ctl border border-amber-300/40 bg-amber-400/15 px-2.5 text-xs font-medium text-amber-50 hover:bg-amber-400/25"
                  >
                    Return to fullscreen
                  </button>
                }
              >
                You left fullscreen. This was recorded.
              </FloatingNotice>
            )}
            {actionError && (
              <FloatingNotice tone="fail" onDismiss={() => setActionError(null)}>
                {actionError}
              </FloatingNotice>
            )}
          </div>
        }
      />

      {exam.phase === "submitted" && !scorecard.open && (
        <SubmittedBanner
          message="Exam submitted. This workspace is now read-only."
          exitLabel="Exit exam"
          testId="exam-submitted-banner"
        />
      )}
      {reviewing && !scorecard.open && (
        <SubmittedBanner
          message={canKeepWorking ? "Submitted. Proctoring has ended." : `Submitted. All ${limit} submissions used.`}
          onKeepWorking={canKeepWorking ? keepWorking : undefined}
        />
      )}

      {breakDialog && (
        <BreakDialog rules={breakRules} error={exam.pauseError} onCancel={() => setBreakDialog(false)} onConfirm={() => void startBreak()} />
      )}
      {onExamBreak && (
        <BreakOverlay
          since={exam.state!.paused_at ? Date.parse(exam.state!.paused_at) : Date.now()}
          rules={breakRules}
          breakNumber={exam.state!.breaks_used ?? 1}
          resuming={exam.starting}
          error={exam.startError}
          onResume={() => void exam.resumeBreak()}
          onTimeUp={() => void exam.refresh()}
        />
      )}
      {!exam.enabled && proctoring.paused && proctoring.pausedSince !== null && (
        <BreakOverlay
          since={proctoring.pausedSince}
          rules={breakRules}
          breakNumber={(proctoring.summary.breaks ?? 0) || 1}
          resuming={false}
          error={null}
          onResume={() => void proctoring.resume({ record: true })}
        />
      )}

      {proctored && !exam.enabled && !proctoring.started && !reviewing && running !== "submit" && (
        <ProctorGate proctoring={proctoring} practical={practical} />
      )}

      {exam.phase === "gate" && (
        <ExamGate
          practical={practical}
          mode={exam.mode}
          sebDetected={exam.sebDetected}
          sebVersion={exam.sebVersion}
          heldElsewhere={exam.heldElsewhere}
          starting={exam.starting}
          error={exam.startError}
          onStart={() => void exam.enter()}
        />
      )}
      {exam.phase === "seb_required" && (
        <SebRequiredGate
          title={practical.title}
          launchUrl={practical.seb_launch_url}
          rejected={exam.sebDetected && exam.sebRejected}
        />
      )}
      {(exam.phase === "locked" || exam.phase === "resume" || exam.phase === "elsewhere") && exam.state && (
        <ExamLockOverlay
          phase={exam.phase}
          state={exam.state}
          starting={exam.starting}
          error={exam.startError}
          onResume={() => void exam.enter()}
        />
      )}

      {confirmOpen && (
        <ConfirmSubmitDialog
          hiddenTests={practical.hidden_test_count}
          endsExam={exam.enabled}
          onCancel={() => setConfirmOpen(false)}
          onConfirm={() => void submit()}
        />
      )}

      {scorecard.open && (
        <RubricScorecardModal
          submission={scorecard.loading ? null : submission}
          loading={scorecard.loading}
          onClose={() => setScorecard({ open: false, loading: false })}
          onViewBreakdown={viewBreakdown}
          exitLabel={exam.enabled ? "Exit exam" : "Exit lab"}
        />
      )}

      {proctoring.toast && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[90] flex justify-center px-4">
          <FloatingNotice tone="fail" onDismiss={proctoring.dismissToast}>
            {proctoring.toast}
          </FloatingNotice>
        </div>
      )}
    </>
  );
}

function DrawerTab({
  active,
  onClick,
  children,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      data-testid={testId}
      className={cx(
        "relative flex items-center gap-1.5 px-3.5 text-xs transition-colors duration-150",
        active ? "text-fg" : "text-fg-faint hover:text-fg-muted",
      )}
    >
      {children}
      <span className={cx("absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand-400 transition-opacity", active ? "opacity-100" : "opacity-0")} />
    </button>
  );
}

/** Same geometry as the loaded workspace, so nothing jumps when data arrives. */
function WorkspaceSkeleton() {
  return (
    <div className="flex h-dvh flex-col bg-canvas" aria-busy="true">
      <div className="flex h-14 items-center gap-3 border-b border-line bg-surface-1 px-4">
        <div className="flex-1 space-y-1.5">
          <DarkSkeleton className="h-3.5 w-72 max-w-full" />
          <DarkSkeleton className="h-2.5 w-44" />
        </div>
        <DarkSkeleton className="hidden h-4 w-[8.5rem] md:block" />
        <DarkSkeleton className="h-8 w-48" />
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.32fr)_minmax(0,1fr)]">
        <div className="flex flex-col border-line bg-surface-1 lg:border-r">
          <div className="flex h-10 items-center gap-3 border-b border-line px-3">
            <DarkSkeleton className="h-4 w-24" />
            <DarkSkeleton className="h-4 w-32" />
          </div>
          <div className="flex-1 space-y-2.5 p-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <DarkSkeleton key={i} className="h-3" />
            ))}
          </div>
        </div>
        <div className="hidden flex-col bg-surface-1 lg:flex">
          <div className="flex h-10 items-center border-b border-line px-3">
            <DarkSkeleton className="h-4 w-28" />
          </div>
          <div className="flex-1 space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <DarkSkeleton key={i} className="h-6" />
            ))}
          </div>
        </div>
      </div>
      <div className="pointer-events-none fixed inset-0 flex items-center justify-center text-sm text-fg-faint">
        <span className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-1.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading lab…
        </span>
      </div>
    </div>
  );
}
