"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PageContainer } from "@/components/AppShell";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  InlineError,
  PageSkeleton,
  SegmentedControl,
  StatTile,
  cx,
  inputCls,
} from "@/components/ui";
import { fmtDuration } from "@/components/workspace/Proctoring";
import { api, fmtScore, getStoredUser } from "@/lib/api";
import { firebaseEnabled, subscribePracticalExams } from "@/lib/firebase";
import { useVisiblePolling } from "@/lib/useVisiblePolling";
import type { ExamStatus, LockdownMode, MonitorResponse, MonitorRow, RiskLevel } from "@/lib/types";
import { PracticalHeader } from "@/app/faculty/_components/PracticalHeader";

// Each poll costs Firestore reads. With Firebase, locks / unlocks also arrive through the exam_live
// listener below at once, so the poll only refreshes counters and test results.
const POLL_MS = firebaseEnabled ? 10_000 : 5_000;

const STATUS_META: Record<ExamStatus, { label: string; tone: "rose" | "emerald" | "slate" | null }> = {
  locked: { label: "Locked", tone: "rose" },
  active: { label: "Working", tone: "emerald" },
  paused: { label: "On break", tone: "slate" },
  not_started: { label: "Not started", tone: null },
  submitted: { label: "Submitted", tone: "slate" },
};

const MODE_LABEL: Record<LockdownMode, string> = {
  off: "Proctoring only",
  exam: "Strict exam",
  seb: "Safe Exam Browser",
};

const th = "px-3 py-2.5 font-medium";

/** "45s" / "3m 10s" since a break started */
function breakFor(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function ago(iso: string | null | undefined, now: number): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`;
}

const Dash = () => <span className="text-slate-400">—</span>;

function RiskBadge({ risk }: { risk: RiskLevel | null }) {
  if (!risk) return <Dash />;
  const label = risk[0].toUpperCase() + risk.slice(1);
  if (risk === "low")
    return (
      <span className="text-xs text-slate-500" title="Integrity indicator for review, not proof">
        {label}
      </span>
    );
  return (
    <span title="Integrity indicator for review, not proof">
      <Badge tone={risk === "high" ? "rose" : "amber"}>{label}</Badge>
    </span>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Non-zero proctoring counters as short text, e.g. "2 pastes · 3 tab switches". */
function ActivitySummary({ row }: { row: MonitorRow }) {
  const items = [
    row.paste_blocked > 0 && plural(row.paste_blocked, "paste", "pastes"),
    row.copy_blocked > 0 && plural(row.copy_blocked, "copy", "copies"),
    row.focus_lost > 0 && plural(row.focus_lost, "tab switch", "tab switches"),
    row.fullscreen_exits > 0 && plural(row.fullscreen_exits, "fullscreen exit", "fullscreen exits"),
    (row.breaks_used ?? 0) > 0 && plural(row.breaks_used!, "break", "breaks"),
  ].filter(Boolean);
  if (items.length === 0 && row.time_away_ms <= 0) return <Dash />;
  return (
    <div
      className="text-xs text-slate-700"
      title="Blocked paste/copy attempts, tab switches, fullscreen exits, and declared breaks (Pause)"
    >
      {items.length > 0 && <p>{items.join(" · ")}</p>}
      {row.time_away_ms > 0 && <p className="mt-0.5 text-slate-500">Away {fmtDuration(row.time_away_ms)}</p>}
    </div>
  );
}

type StatusFilter = "all" | "locked" | "active" | "submitted";

export default function LiveLabMonitorPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<MonitorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [lockTarget, setLockTarget] = useState<MonitorRow | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [now, setNow] = useState(() => Date.now());
  const seqRef = useRef(0);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const res = await api.monitor(id);
      if (seq !== seqRef.current) return;
      hasDataRef.current = true;
      setData(res);
      setError(null);
      setPollError(null);
    } catch (e) {
      if (seq !== seqRef.current) return;
      const msg = e instanceof Error ? e.message : "Could not load monitor";
      if (hasDataRef.current) setPollError(`Live updates paused: ${msg}`);
      else setError(msg);
    }
  }, [id]);

  useVisiblePolling(() => void load(), POLL_MS); // paused while the tab is hidden
  useEffect(() => {
    const clock = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(clock);
  }, []);

  const [liveConnected, setLiveConnected] = useState(false);
  useEffect(() => {
    if (!firebaseEnabled) return;
    const me = getStoredUser()?.id;
    if (!me) return;
    let last: string | null = null;
    const unsub = subscribePracticalExams(
      id,
      me,
      (docs) => {
        setLiveConnected(true);
        const sig = docs.map((d) => `${d.student_id}:${d.status}:${d.violations}`).sort().join(",");
        if (last !== null && sig !== last) void load();
        last = sig;
      },
      () => setLiveConnected(false),
    );
    return () => {
      unsub();
      setLiveConnected(false);
    };
  }, [id, load]);

  async function unlock(row: MonitorRow) {
    setBusy(row.student_id);
    setActionError(null);
    try {
      await api.unlockExam(id, row.student_id);
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unlock failed");
    } finally {
      setBusy(null);
    }
  }

  async function lock(row: MonitorRow, reason: string) {
    setBusy(row.student_id);
    setActionError(null);
    try {
      await api.lockExam(id, row.student_id, reason);
      setLockTarget(null);
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Lock failed");
    } finally {
      setBusy(null);
    }
  }

  const filteredRows = useMemo(() => {
    if (!data) return [];
    if (statusFilter === "all") return data.rows;
    return data.rows.filter((r) => r.status === statusFilter);
  }, [data, statusFilter]);

  if (!data && !error)
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  if (!data)
    return (
      <PageContainer>
        <ErrorState message={error ?? "Not found"} onRetry={load} />
      </PageContainer>
    );

  const lockdown = data.lockdown_mode !== "off";
  const { counts } = data;
  const filterOptions: { value: StatusFilter; label: string }[] = [
    { value: "all", label: "All" },
    ...(lockdown ? [{ value: "locked" as const, label: "Locked" }] : []),
    { value: "active", label: "Working" },
    { value: "submitted", label: "Submitted" },
  ];

  return (
    <PageContainer>
      <PracticalHeader
        practicalId={id}
        title={data.practical_title}
        subtitle={
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>
              {data.course_code} · {MODE_LABEL[data.lockdown_mode]}
            </span>
            <span className="inline-flex items-center gap-1.5" data-testid="monitor-updated">
              <span
                aria-hidden
                className={cx("inline-block h-1.5 w-1.5 rounded-full", pollError ? "bg-amber-500" : "bg-emerald-500")}
              />
              Updated {ago(data.generated_at, now)}
            </span>
            {liveConnected && (
              <span
                className="text-slate-400"
                title="Real-time lock updates via Cloud Firestore"
                data-testid="monitor-firestore-live"
              >
                Live
              </span>
            )}
          </span>
        }
        activeTab="monitor"
      />

      <div className={cx("grid grid-cols-2 gap-4", lockdown ? "md:grid-cols-4" : "md:grid-cols-3")} data-testid="monitor-counts">
        {lockdown && (
          <StatTile
            label="Locked"
            value={<span className={counts.locked > 0 ? "text-rose-700" : undefined}>{counts.locked}</span>}
          />
        )}
        <StatTile
          label="Working"
          value={counts.active}
          hint={`${counts.online} online${counts.paused ? ` · ${counts.paused} on break` : ""}`}
        />
        <StatTile label="Not started" value={counts.not_started} />
        <StatTile label="Submitted" value={counts.submitted} />
      </div>

      {(pollError || actionError) && (
        <div className="mt-4 space-y-2">
          <InlineError message={actionError} />
          <InlineError message={pollError} />
        </div>
      )}

      <Card className="mt-6">
        <CardHeader
          title="Students"
          subtitle={`${data.rows.length} enrolled`}
          action={
            data.rows.length > 0 ? (
              <SegmentedControl
                ariaLabel="Filter students"
                value={statusFilter}
                onChange={setStatusFilter}
                options={filterOptions}
              />
            ) : undefined
          }
        />
        {filteredRows.length === 0 ? (
          <EmptyState title={data.rows.length === 0 ? "No students enrolled." : "No students match this filter."} />
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm" data-testid="monitor-table">
              <thead className="text-xs text-slate-500">
                <tr className="border-b border-slate-100">
                  <th className={cx(th, "min-w-44 pl-5")}>Student</th>
                  <th className={cx(th, "min-w-48")}>Status</th>
                  <th className={th}>Activity</th>
                  <th className={th}>Score</th>
                  <th className={th}>Integrity</th>
                  <th className={cx(th, "pr-5")}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredRows.map((r) => {
                  const meta = STATUS_META[r.status];
                  return (
                    <tr
                      key={r.student_id}
                      data-testid="monitor-row"
                      data-student={r.student_name}
                      data-status={r.status}
                      className={cx("align-top", r.status === "locked" ? "bg-rose-50/50" : "hover:bg-slate-50/60")}
                    >
                      <td className="py-3 pl-5 pr-3">
                        <p className="font-medium text-slate-900">{r.student_name}</p>
                        <p className="font-mono text-xs text-slate-500">{r.roll_number ?? "—"}</p>
                      </td>
                      <td className="max-w-xs px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {meta.tone ? (
                            <Badge tone={meta.tone}>{meta.label}</Badge>
                          ) : (
                            <span className="text-xs text-slate-500">{meta.label}</span>
                          )}
                          {(r.online || r.last_seen_at) && (
                            <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-slate-500">
                              {r.online && <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-emerald-500" />}
                              {r.online ? "Online" : `Seen ${ago(r.last_seen_at, now)}`}
                            </span>
                          )}
                        </div>
                        {r.status === "paused" && r.paused_at && (
                          <p className="mt-1 text-xs text-slate-600" data-testid="monitor-break">
                            On break for {breakFor(r.paused_at, now)} · break {r.breaks_used ?? 1}
                          </p>
                        )}
                        {r.status === "locked" && (
                          <p className="mt-1 text-xs font-medium text-rose-700" data-testid="monitor-lock-reason">
                            {r.lock_reason ?? "Locked"}
                            {r.locked_at && <span className="font-normal text-slate-500"> · {ago(r.locked_at, now)}</span>}
                          </p>
                        )}
                        {(r.violations > 0 || r.unlock_count > 0) && (
                          <p className="mt-0.5 text-xs text-slate-500">
                            {plural(r.violations, "violation", "violations")} · {plural(r.unlock_count, "unlock", "unlocks")}
                          </p>
                        )}
                      </td>
                      <td className="max-w-[15rem] px-3 py-3">
                        <ActivitySummary row={r} />
                      </td>
                      <td className="px-3 py-3 tabular-nums">
                        <p className="font-medium text-slate-900">
                          {r.final_score !== null ? fmtScore(r.final_score, r.max_score) : <Dash />}
                        </p>
                        {r.tests_total ? (
                          <p className="mt-0.5 text-xs text-slate-500">
                            {r.tests_passed}/{r.tests_total} tests
                          </p>
                        ) : null}
                      </td>
                      <td className="px-3 py-3">
                        <RiskBadge risk={r.integrity_risk} />
                      </td>
                      <td className="py-3 pl-3 pr-5">
                        <div className="flex items-center justify-end gap-3 whitespace-nowrap">
                          {lockdown && r.status === "locked" && (
                            <Button
                              size="sm"
                              loading={busy === r.student_id}
                              onClick={() => void unlock(r)}
                              data-testid="monitor-unlock"
                            >
                              Unlock
                            </Button>
                          )}
                          {lockdown && r.status === "active" && (
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={busy === r.student_id}
                              onClick={() => setLockTarget(r)}
                              data-testid="monitor-lock"
                            >
                              Lock
                            </Button>
                          )}
                          {r.submission_id && (
                            <Link
                              href={`/faculty/submissions/${r.submission_id}`}
                              className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
                            >
                              Review
                            </Link>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          Indicators for review, not proof. Talk to the student before acting.
          {!lockdown && " Exam lockdown is off for this lab."}
        </p>
      </Card>

      {lockTarget && (
        <LockDialog
          row={lockTarget}
          busy={busy === lockTarget.student_id}
          onCancel={() => setLockTarget(null)}
          onConfirm={(reason) => void lock(lockTarget, reason)}
        />
      )}
    </PageContainer>
  );
}

function LockDialog({
  row,
  busy,
  onCancel,
  onConfirm,
}: {
  row: MonitorRow;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Lock exam"
      data-testid="lock-dialog"
    >
      <form
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-md"
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(reason);
        }}
      >
        <h2 className="text-base font-semibold text-slate-900">Lock {row.student_name}&apos;s exam?</h2>
        <p className="mt-1 text-sm text-slate-600">
          Blocks their workspace until unlocked. The reason is shown to the student.
        </p>
        <div className="mt-4">
          <Field label="Reason (optional)">
            <input
              ref={inputRef}
              className={inputCls}
              maxLength={200}
              value={reason}
              placeholder="e.g. Phone on desk"
              onChange={(e) => setReason(e.target.value)}
              data-testid="lock-reason-input"
            />
          </Field>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" loading={busy} data-testid="lock-confirm">
            Lock exam
          </Button>
        </div>
      </form>
    </div>
  );
}
