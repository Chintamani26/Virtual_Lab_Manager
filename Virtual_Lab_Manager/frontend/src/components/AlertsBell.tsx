"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, BellRing } from "lucide-react";
import { api, getStoredUser } from "@/lib/api";
import { firebaseEnabled, subscribeLockedExams } from "@/lib/firebase";
import { useVisiblePolling } from "@/lib/useVisiblePolling";
import type { AlertsResponse } from "@/lib/types";
import { cx } from "./ui";

const POLL_MS = 10_000;

function ago(iso: string | null): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ago` : `${Math.floor(m / 60)}h ago`;
}

/**
 * Faculty / HOD notification bell (docs/API.md v1.2): polls GET /faculty/alerts and lists students whose
 * exams are locked, each linking to that lab's Live Lab Monitor where they can be unlocked.
 * With Firebase configured, a Firestore listener on exam_live makes the badge update the moment a
 * student is locked or unlocked; polling stays on as the fallback.
 */
export function AlertsBell() {
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.alerts());
    } catch {
      /* best effort — the bell just keeps its last value */
    }
  }, []);

  useVisiblePolling(() => void load(), POLL_MS); // paused while the tab is hidden

  // Firebase real-time: reload the moment the set of locked students changes.
  useEffect(() => {
    if (!firebaseEnabled) return;
    const me = getStoredUser()?.id;
    if (!me) return;
    let last: string | null = null;
    return subscribeLockedExams(me, (docs) => {
      const sig = docs.map((d) => `${d.practical_id}:${d.student_id}:${d.violations}`).sort().join(",");
      if (last !== null && sig !== last) void load();
      last = sig;
    });
  }, [load]);

  useEffect(() => {
    if (!open) return;
    void load();
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, load]);

  const count = data?.locked_count ?? 0;
  const Icon = count > 0 ? BellRing : Bell;

  return (
    <div ref={rootRef} className="relative" data-testid="alerts-bell">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={count > 0 ? `${count} locked exam${count === 1 ? "" : "s"}` : "No exam alerts"}
        title={count > 0 ? `${count} student${count === 1 ? "" : "s"} locked out of an exam` : "Exam alerts"}
        className={cx(
          "relative inline-flex h-8 w-8 items-center justify-center rounded-md transition",
          count > 0 ? "text-rose-300 hover:bg-rose-500/10" : "text-slate-400 hover:bg-slate-900 hover:text-white",
        )}
      >
        <Icon className="h-[18px] w-[18px]" />
        {count > 0 && (
          <span
            className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 font-mono text-[10px] font-semibold leading-none text-white ring-2 ring-slate-950"
            data-testid="alerts-count"
          >
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="fixed inset-x-4 top-14 z-50 mt-2 animate-pop-in overflow-hidden rounded-lg border border-slate-200 bg-white text-sm text-slate-900 shadow-md sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:w-80"
        >
          <p className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold text-slate-900">Locked exams</p>
          {count === 0 ? (
            <p className="px-4 py-4 text-sm text-slate-500">No students are locked out.</p>
          ) : (
            <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
              {data!.locked.map((a) => (
                <li key={`${a.practical_id}:${a.student_id}`}>
                  <Link
                    href={`/faculty/practicals/${a.practical_id}/monitor`}
                    onClick={() => setOpen(false)}
                    className="block px-4 py-2.5 transition-colors hover:bg-slate-50"
                    data-testid="alert-item"
                  >
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate font-medium text-slate-900">{a.student_name}</span>
                      <span className="shrink-0 text-xs text-slate-400">{ago(a.locked_at)}</span>
                    </span>
                    <span className="block truncate text-xs text-slate-500">
                      {a.course_code} · {a.practical_title}
                    </span>
                    {a.lock_reason && <span className="mt-0.5 block truncate text-xs text-rose-700">{a.lock_reason}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
