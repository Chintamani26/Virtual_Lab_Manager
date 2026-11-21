"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { Badge, Card, CardHeader, cx } from "./ui";
import { api, fmtDate } from "@/lib/api";
import type { IntegrityReport, IntegritySeverity, ProctorEventOut, RiskLevel } from "@/lib/types";

const RISK: Record<RiskLevel, { label: string; tone: "emerald" | "amber" | "rose"; text: string }> = {
  low: { label: "Low", tone: "emerald", text: "text-slate-900" },
  medium: { label: "Medium", tone: "amber", text: "text-amber-700" },
  high: { label: "High", tone: "rose", text: "text-rose-700" },
};

export function fmtDuration(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Compact risk label for tables: "High · 87% AI". Low risk is plain text; medium/high get a status badge. */
export function IntegrityBadge({ integrity }: { integrity: IntegrityReport | null | undefined }) {
  if (!integrity) return null;
  const r = RISK[integrity.risk_level] ?? RISK.low;
  const text = `${r.label} · ${Math.round(integrity.ai_likelihood)}% AI`;
  if (integrity.risk_level === "low") return <span className="whitespace-nowrap text-xs tabular-nums text-slate-500">{text}</span>;
  return (
    <Badge tone={r.tone} className="tabular-nums">
      {text}
    </Badge>
  );
}

const SEVERITY_DOT: Record<IntegritySeverity, string> = {
  critical: "bg-rose-500",
  warning: "bg-amber-500",
  info: "bg-slate-300",
};

function Stat({ label, value, warn }: { label: string; value: React.ReactNode; warn?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className={cx("mt-0.5 text-sm font-medium tabular-nums", warn ? "text-amber-700" : "text-slate-900")}>{value}</dd>
    </div>
  );
}

export function IntegrityCard({ submissionId, integrity }: { submissionId: string; integrity: IntegrityReport | null | undefined }) {
  const [detailsOpen, setDetailsOpen] = useState(integrity?.risk_level === "high");

  if (!integrity) {
    return (
      <Card>
        <CardHeader title="Integrity" />
        <p className="px-5 py-4 text-sm text-slate-500">No integrity report available.</p>
      </Card>
    );
  }
  const r = RISK[integrity.risk_level] ?? RISK.low;
  const p = integrity.proctoring;
  const signals = [...integrity.signals].sort((a, b) => b.weight - a.weight);
  const sim = integrity.similarity;
  const simPct = Math.round((sim.max_peer_similarity ?? 0) * 100);

  return (
    <Card>
      <CardHeader
        title="Integrity"
        action={
          <Badge tone={r.tone} className="tabular-nums">
            {r.label} · {Math.round(integrity.ai_likelihood)}% AI
          </Badge>
        }
      />

      <div className="space-y-3 px-5 py-4">
        <p className="text-sm text-slate-700">{integrity.summary}</p>

        {sim.peer_submission_id && simPct > 0 && (
          <p className="text-sm text-slate-700">
            <span className={cx("font-medium", simPct >= 85 ? "text-rose-700" : "text-slate-900")}>{simPct}% similar</span> to{" "}
            <Link href={`/faculty/submissions/${sim.peer_submission_id}`} className="font-medium text-indigo-600 hover:text-indigo-500">
              {sim.peer_student_name ?? "a classmate"}&apos;s submission
            </Link>
          </p>
        )}

        {signals.length > 0 && (
          <ul className="divide-y divide-slate-100 border-t border-slate-100 pt-2">
            {signals.map((sg) => (
              <li key={sg.key} className="flex gap-2.5 py-2 first:pt-1 last:pb-0">
                <span
                  aria-hidden
                  title={sg.severity}
                  className={cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", SEVERITY_DOT[sg.severity] ?? SEVERITY_DOT.info)}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">{sg.label}</p>
                  <p className="text-xs text-slate-500">{sg.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Collapsible proctoring & content telemetry */}
      <div className="border-t border-slate-100">
        <button
          type="button"
          onClick={() => setDetailsOpen((o) => !o)}
          aria-expanded={detailsOpen}
          className="flex w-full items-center gap-2 px-5 py-3 text-left text-sm font-medium text-slate-900 hover:bg-slate-50"
        >
          {detailsOpen ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
          <span>Proctoring &amp; analysis</span>
          <span className="ml-auto text-xs font-normal tabular-nums text-slate-500">
            Risk {Math.round(integrity.risk_score)}/100
          </span>
        </button>

        {detailsOpen && (
          <div className="space-y-4 px-5 pb-4 pt-1">
            {!p.proctored ? (
              <p className="text-sm text-slate-500">Lab was not proctored.</p>
            ) : (
              <div>
                <dl className="grid grid-cols-3 gap-x-4 gap-y-3">
                  <Stat label="Sessions" value={p.sessions} warn={p.sessions === 0} />
                  <Stat label="Pastes" value={p.paste_blocked} warn={p.paste_blocked > 0} />
                  <Stat label="Copies" value={p.copy_blocked} warn={p.copy_blocked > 2} />
                  <Stat label="Tab switches" value={p.focus_lost} warn={p.focus_lost >= 5} />
                  <Stat label="Time away" value={fmtDuration(p.time_away_ms)} warn={p.time_away_ms >= 180_000} />
                  <Stat label="Fullscreen exits" value={p.fullscreen_exits} warn={p.fullscreen_exits >= 3} />
                  <Stat label="Dev-tools" value={p.devtools_blocked} warn={p.devtools_blocked > 0} />
                  <Stat label="Large edits" value={p.large_insertions} warn={p.large_insertions > 0} />
                  <Stat label="Max burst" value={`${p.max_burst_cps} cps`} warn={p.max_burst_cps > 30} />
                </dl>
                <p className="mt-3 text-xs text-slate-500">
                  <span className="tabular-nums">{p.typed_chars.toLocaleString()}</span> typed /{" "}
                  <span className="tabular-nums">{p.new_code_chars.toLocaleString()}</span> new chars
                  {p.typed_ratio !== null && (
                    <>
                      {" · ratio "}
                      <span className={cx("font-medium tabular-nums", p.typed_ratio < 0.6 ? "text-rose-700" : "text-slate-900")}>
                        {p.typed_ratio.toFixed(2)}
                      </span>
                    </>
                  )}
                </p>
              </div>
            )}

            <div className="border-t border-slate-100 pt-3">
              <div className="mb-1.5 flex items-baseline justify-between gap-2">
                <p className="text-xs font-medium text-slate-500">Content analysis</p>
                <span className="font-mono text-[11px] text-slate-400">
                  {Math.round(integrity.content.ai_style_score)} · {integrity.content.model}
                </span>
              </div>
              {integrity.content.indicators.length === 0 ? (
                <p className="text-xs text-slate-500">No AI-style patterns detected.</p>
              ) : (
                <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600 marker:text-slate-300">
                  {integrity.content.indicators.map((ind, i) => (
                    <li key={i}>{ind}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

      <ProctorTimeline submissionId={submissionId} />

      <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
        Indicators for review, not proof.
      </p>
    </Card>
  );
}

// ---------- timeline ----------
const EVENT_LABEL: Record<string, string> = {
  session_start: "Proctored session started",
  paste_blocked: "Paste blocked",
  copy_blocked: "Copy blocked",
  cut_blocked: "Cut blocked",
  drop_blocked: "Drag-and-drop blocked",
  context_menu_blocked: "Right-click blocked",
  devtools_blocked: "Dev-tools shortcut blocked",
  focus_lost: "Left lab window",
  fullscreen_exit: "Exited fullscreen",
  large_insertion: "Large code insertion",
  typing_stats: "Typing snapshot",
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function eventDetail(e: ProctorEventOut): string {
  const d = e.detail ?? {};
  switch (e.type) {
    case "session_start":
      return d.fullscreen === true ? "fullscreen" : d.fullscreen === false ? "not fullscreen" : "";
    case "focus_lost": {
      const ms = num(d.duration_ms);
      const reason = d.reason === "tab_hidden" ? "switched tab" : d.reason === "window_blur" ? "switched window" : "";
      return [ms !== null ? `away ${fmtDuration(ms)}` : "", reason].filter(Boolean).join(" · ");
    }
    case "large_insertion": {
      const chars = num(d.chars);
      return chars !== null ? `${chars} chars in one edit` : "";
    }
    case "typing_stats": {
      const typed = num(d.typed_chars);
      const keys = num(d.keystrokes);
      const burst = num(d.max_burst_cps);
      const active = num(d.active_ms);
      return [
        typed !== null ? `${typed} chars typed` : "",
        keys !== null ? `${keys} keystrokes` : "",
        active !== null ? `${fmtDuration(active)} active` : "",
        burst !== null ? `max ${burst} cps` : "",
      ]
        .filter(Boolean)
        .join(" · ");
    }
    default:
      return "";
  }
}

function ago(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(diff)) return "";
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function summarise(events: ProctorEventOut[]): ProctorEventOut[] {
  const lastStats = new Map<string, string>();
  for (const e of events) if (e.type === "typing_stats") lastStats.set(e.session_id, e.id);
  return events.filter((e) => e.type !== "typing_stats" || lastStats.get(e.session_id) === e.id);
}

function ProctorTimeline({ submissionId }: { submissionId: string }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<ProctorEventOut[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && events === null && !loading) {
      setLoading(true);
      setError(null);
      try {
        setEvents(await api.submissionProctorEvents(submissionId));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load timeline");
      } finally {
        setLoading(false);
      }
    }
  }

  const shown = events ? summarise(events) : [];
  const sessions = events ? new Set(events.map((e) => e.session_id)).size : 0;

  return (
    <div className="border-t border-slate-100">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-5 py-3 text-left text-sm font-medium text-slate-900 hover:bg-slate-50"
      >
        {open ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
        <span>Proctoring timeline</span>
        {events && (
          <span className="ml-auto text-xs font-normal text-slate-500">
            {events.length} events · {sessions} session{sessions === 1 ? "" : "s"}
          </span>
        )}
      </button>
      {open && (
        <div className="max-h-72 overflow-auto px-5 pb-4">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </p>
          ) : error ? (
            <p className="text-sm text-rose-600">{error}</p>
          ) : shown.length === 0 ? (
            <p className="text-sm text-slate-500">No proctoring events recorded.</p>
          ) : (
            <ol className="divide-y divide-slate-100">
              {shown.map((e) => {
                const detail = eventDetail(e);
                return (
                  <li key={e.id} className="flex items-baseline justify-between gap-4 py-2">
                    <p className="min-w-0 text-xs text-slate-800">
                      {EVENT_LABEL[e.type] ?? e.type}
                      {detail && <span className="text-slate-500"> · {detail}</span>}
                    </p>
                    <p
                      className="shrink-0 text-xs tabular-nums text-slate-500"
                      title={`${fmtDate(e.occurred_at, true)} · ${ago(e.occurred_at)}`}
                    >
                      {fmtDate(e.occurred_at, true)}
                    </p>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
