"use client";

/**
 * Client-side proctoring for a lab session (docs/API.md v1.1).
 *
 * - Blocks copy / cut / paste / drag-drop / right-click and common developer-tools shortcuts,
 *   recording every attempt.
 * - Records focus loss (tab hidden / window blur) with duration, and fullscreen exits.
 * - Collects typing telemetry (TypingStats) so faculty can compare typed vs. submitted code.
 * - Batches events to `POST /student/practicals/{id}/proctor/events`; network failures are
 *   swallowed and retried on the next flush so the IDE never breaks.
 *
 * Browser-side blocking can be bypassed by a determined student — that's why every
 * attempt is recorded and the server builds an integrity report from the evidence.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ProctorEventIn, ProctorEventType, ProctorSummary, TypingStats } from "@/lib/types";

export type BlockedType =
  | "paste_blocked"
  | "copy_blocked"
  | "cut_blocked"
  | "drop_blocked"
  | "context_menu_blocked"
  | "devtools_blocked";

export interface EditChange {
  /** number of characters inserted by this change (0 for pure deletions) */
  inserted: number;
  /** model was replaced wholesale (load / setValue) — never counted */
  isFlush: boolean;
  /** undo / redo — never counted */
  isUndoRedo: boolean;
}

export interface Proctoring {
  enabled: boolean;
  /** uuid of this page load's proctoring session — also the exam session id (docs/API.md v1.2) */
  sessionId: string;
  started: boolean;
  start: () => Promise<void>;
  summary: ProctorSummary;
  toast: string | null;
  dismissToast: () => void;
  fullscreenLost: boolean;
  returnToFullscreen: () => void;
  recordBlocked: (type: BlockedType) => void;
  recordChange: (c: EditChange) => void;
  recordKeystroke: () => void;
  /** send queued events + stats now (await before Submit) */
  flush: () => Promise<void>;
  /** run a blocking dialog (window.confirm) without logging it as focus loss */
  suppressFocusTracking: <T>(fn: () => T) => T;
  /** on a declared break (Pause button): leaving the window or fullscreen isn't recorded */
  paused: boolean;
  /** when the current break started (ms since epoch), null when not paused */
  pausedSince: number | null;
  /** start a break; `record` = log break_start (proctored labs; the server logs exam breaks itself) */
  pause: (opts: { record: boolean }) => void;
  /** end the break (call from a click: re-enters fullscreen) */
  resume: (opts: { record: boolean }) => Promise<void>;
  /**
   * End the session when the work is handed in: sends what's queued, then nothing (tab switches,
   * fullscreen exits, typing) is recorded any more. start() opens it again.
   */
  end: () => Promise<void>;
}

export const EMPTY_SUMMARY: ProctorSummary = {
  sessions: 0,
  paste_blocked: 0,
  copy_blocked: 0,
  focus_lost: 0,
  time_away_ms: 0,
  fullscreen_exits: 0,
  devtools_blocked: 0,
  large_insertions: 0,
};

const EMPTY_STATS: TypingStats = {
  typed_chars: 0,
  keystrokes: 0,
  active_ms: 0,
  large_insertions: 0,
  large_insertion_chars: 0,
  max_burst_cps: 0,
};

const LARGE_INSERTION = 60; // chars in a single editor change
const ACTIVE_GAP_MS = 30_000; // gaps longer than this are idle time
const BURST_WINDOW_MS = 2_000;
const FLUSH_EVERY_MS = 10_000;
const FLUSH_AT_QUEUE = 20;
const MAX_BATCH = 100; // contract: max 100 events per request
const MAX_QUEUE = 500; // cap retries if the API is unreachable
const MIN_AWAY_MS = 800; // ignore micro blurs

/** " — this attempt was recorded." is appended only while a session is recording */
const TOASTS: Record<BlockedType, string> = {
  paste_blocked: "Copy/paste is disabled in proctored labs",
  copy_blocked: "Copy/paste is disabled in proctored labs",
  cut_blocked: "Copy/paste is disabled in proctored labs",
  drop_blocked: "Drag-and-drop is disabled in proctored labs",
  context_menu_blocked: "Right-click is disabled in proctored labs",
  devtools_blocked: "Developer tools are disabled in proctored labs",
};

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // RFC4122-ish fallback for non-secure contexts
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/** Apply one event to a summary (local, optimistic accounting). */
function bump(s: ProctorSummary, type: ProctorEventType, detail?: ProctorEventIn["detail"]): ProctorSummary {
  switch (type) {
    case "session_start":
      return { ...s, sessions: s.sessions + 1 };
    case "paste_blocked":
      return { ...s, paste_blocked: s.paste_blocked + 1 };
    case "copy_blocked":
    case "cut_blocked":
      return { ...s, copy_blocked: s.copy_blocked + 1 };
    case "focus_lost":
      return {
        ...s,
        focus_lost: s.focus_lost + 1,
        time_away_ms: s.time_away_ms + (typeof detail?.duration_ms === "number" ? detail.duration_ms : 0),
      };
    case "fullscreen_exit":
      return { ...s, fullscreen_exits: s.fullscreen_exits + 1 };
    case "devtools_blocked":
      return { ...s, devtools_blocked: s.devtools_blocked + 1 };
    case "large_insertion":
      return { ...s, large_insertions: s.large_insertions + 1 };
    case "break_start":
      return { ...s, breaks: (s.breaks ?? 0) + 1 };
    case "break_end":
      return { ...s, break_ms: (s.break_ms ?? 0) + (typeof detail?.duration_ms === "number" ? detail.duration_ms : 0) };
    default:
      return s;
  }
}

export function isDevtoolsCombo(e: KeyboardEvent): boolean {
  if (e.key === "F12") return true;
  const devKey = e.code === "KeyI" || e.code === "KeyJ" || e.code === "KeyC";
  if (e.ctrlKey && e.shiftKey && devKey) return true; // Windows / Linux
  if (e.metaKey && e.altKey && devKey) return true; // macOS Cmd+Opt+I/J/C
  if ((e.ctrlKey || e.metaKey) && e.code === "KeyU") return true; // view source (incl. Cmd+Opt+U)
  return false;
}

export function useProctoring(
  practicalId: string,
  enabled: boolean,
  initialSummary: ProctorSummary | null | undefined,
): Proctoring {
  const [started, setStarted] = useState(false);
  const [summary, setSummary] = useState<ProctorSummary>(initialSummary ?? EMPTY_SUMMARY);
  const [toast, setToast] = useState<string | null>(null);
  const [fullscreenLost, setFullscreenLost] = useState(false);
  const [pausedSince, setPausedSince] = useState<number | null>(null);
  const pausedRef = useRef<number | null>(null);

  const sessionIdRef = useRef<string>("");
  if (!sessionIdRef.current) sessionIdRef.current = uuid();

  const startedRef = useRef(false);
  const queueRef = useRef<ProctorEventIn[]>([]);
  const statsRef = useRef<TypingStats>({ ...EMPTY_STATS });
  const statsDirtyRef = useRef(false);
  const lastEditAtRef = useRef<number | null>(null);
  const burstRef = useRef<{ t: number; n: number }[]>([]);
  const flushingRef = useRef<Promise<void> | null>(null);
  const awayRef = useRef<{ start: number; reason: "tab_hidden" | "window_blur" } | null>(null);
  const suppressRef = useRef(0);
  const wasFullscreenRef = useRef(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seededRef = useRef(false);

  // seed the summary from the server once it arrives (practical loads async)
  useEffect(() => {
    if (initialSummary && !seededRef.current) {
      seededRef.current = true;
      setSummary(initialSummary);
    }
  }, [initialSummary]);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3500);
  }, []);

  // ---------- transport ----------
  const sendBatch = useCallback(
    async (keepalive: boolean) => {
      const events = queueRef.current.splice(0, MAX_BATCH);
      const statsChanged = statsDirtyRef.current;
      if (events.length === 0 && !statsChanged) return;
      statsDirtyRef.current = false;
      try {
        const res = await api.proctorEvents(
          practicalId,
          { session_id: sessionIdRef.current, events, stats: { ...statsRef.current } },
          { keepalive },
        );
        // server summary is authoritative; re-apply anything still queued locally
        let next = res.summary;
        for (const ev of queueRef.current) next = bump(next, ev.type, ev.detail);
        setSummary(next);
      } catch {
        // never break the IDE: put the batch back and retry on the next flush
        queueRef.current = [...events, ...queueRef.current].slice(-MAX_QUEUE);
        if (statsChanged) statsDirtyRef.current = true;
      }
    },
    [practicalId],
  );

  const flush = useCallback(
    async (keepalive = false) => {
      if (!enabled) return;
      // serialise flushes so batches/stats arrive in order
      const prev = flushingRef.current ?? Promise.resolve();
      const run = prev.then(async () => {
        await sendBatch(keepalive);
        // drain if more than one batch is queued
        while (queueRef.current.length >= MAX_BATCH) {
          const before = queueRef.current.length;
          await sendBatch(keepalive);
          if (queueRef.current.length >= before) break; // failing — stop
        }
      });
      flushingRef.current = run.finally(() => {
        if (flushingRef.current === run) flushingRef.current = null;
      });
      await run;
    },
    [enabled, sendBatch],
  );

  const enqueue = useCallback(
    (type: ProctorEventType, detail?: ProctorEventIn["detail"]) => {
      const ev: ProctorEventIn = { type, at: new Date().toISOString(), ...(detail ? { detail } : {}) };
      queueRef.current.push(ev);
      if (queueRef.current.length > MAX_QUEUE) queueRef.current.splice(0, queueRef.current.length - MAX_QUEUE);
      setSummary((s) => bump(s, type, detail));
      if (queueRef.current.length >= FLUSH_AT_QUEUE) void flush();
    },
    [flush],
  );

  const recordBlocked = useCallback(
    (type: BlockedType) => {
      if (!enabled) return;
      showToast(startedRef.current ? `${TOASTS[type]} — this attempt was recorded.` : `${TOASTS[type]}.`);
      if (startedRef.current) enqueue(type);
    },
    [enabled, enqueue, showToast],
  );

  // ---------- typing telemetry ----------
  const recordChange = useCallback(
    ({ inserted, isFlush, isUndoRedo }: EditChange) => {
      if (!enabled || !startedRef.current || isFlush || isUndoRedo) return;
      const now = performance.now();
      const stats = statsRef.current;
      if (lastEditAtRef.current !== null) {
        const gap = now - lastEditAtRef.current;
        if (gap < ACTIVE_GAP_MS) stats.active_ms = Math.round(stats.active_ms + gap);
      }
      lastEditAtRef.current = now;
      statsDirtyRef.current = true;
      if (inserted <= 0) return;

      if (inserted >= LARGE_INSERTION) {
        stats.large_insertions += 1;
        stats.large_insertion_chars += inserted;
        enqueue("large_insertion", { chars: inserted });
        return;
      }

      stats.typed_chars += inserted;
      const burst = burstRef.current;
      burst.push({ t: now, n: inserted });
      while (burst.length && now - burst[0].t > BURST_WINDOW_MS) burst.shift();
      const cps = burst.reduce((a, b) => a + b.n, 0) / (BURST_WINDOW_MS / 1000);
      if (cps > stats.max_burst_cps) stats.max_burst_cps = Math.round(cps * 10) / 10;
    },
    [enabled, enqueue],
  );

  const recordKeystroke = useCallback(() => {
    if (!enabled || !startedRef.current) return;
    statsRef.current.keystrokes += 1;
    statsDirtyRef.current = true;
  }, [enabled]);

  // ---------- session start ----------
  const start = useCallback(async () => {
    if (!enabled || startedRef.current) return;
    let fullscreen = false;
    try {
      if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      }
      fullscreen = !!document.fullscreenElement;
    } catch {
      fullscreen = false; // unsupported / denied — still start the session
    }
    wasFullscreenRef.current = fullscreen;
    startedRef.current = true;
    setStarted(true);
    enqueue("session_start", {
      fullscreen,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
    });
    await flush();
  }, [enabled, enqueue, flush]);

  const returnToFullscreen = useCallback(() => {
    document.documentElement
      .requestFullscreen?.()
      .then(() => {
        wasFullscreenRef.current = true;
        setFullscreenLost(false);
      })
      .catch(() => undefined);
  }, []);

  const suppressFocusTracking = useCallback(<T,>(fn: () => T): T => {
    suppressRef.current += 1;
    try {
      return fn();
    } finally {
      // blur/focus events from the dialog are dispatched asynchronously
      setTimeout(() => {
        suppressRef.current = Math.max(0, suppressRef.current - 1);
        awayRef.current = null;
      }, 300);
    }
  }, []);

  // ---------- blocking listeners (active whenever the lab is proctored) ----------
  useEffect(() => {
    if (!enabled) return;
    const block = (type: BlockedType | null) => (e: Event) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      if (type) recordBlocked(type);
    };
    const handlers: [string, EventListener][] = [
      ["copy", block("copy_blocked")],
      ["cut", block("cut_blocked")],
      ["paste", block("paste_blocked")],
      ["drop", block("drop_blocked")],
      ["dragstart", block(null)], // stop dragging text out silently
      ["contextmenu", block("context_menu_blocked")],
    ];
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isDevtoolsCombo(e)) return;
      e.preventDefault();
      e.stopPropagation();
      recordBlocked("devtools_blocked");
    };
    for (const [type, h] of handlers) document.addEventListener(type, h, true);
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      for (const [type, h] of handlers) document.removeEventListener(type, h, true);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [enabled, recordBlocked]);

  // ---------- focus / visibility / fullscreen (after the session starts) ----------
  useEffect(() => {
    if (!enabled || !started) return;

    const markAway = (reason: "tab_hidden" | "window_blur") => {
      // startedRef: end() may run before React removes these listeners
      if (!startedRef.current || suppressRef.current > 0 || pausedRef.current !== null) return;
      if (!awayRef.current) awayRef.current = { start: Date.now(), reason };
      else if (reason === "tab_hidden") awayRef.current.reason = "tab_hidden";
    };
    const markBack = () => {
      const away = awayRef.current;
      awayRef.current = null;
      if (!away || suppressRef.current > 0 || pausedRef.current !== null) return;
      const duration = Date.now() - away.start;
      if (duration < MIN_AWAY_MS) return;
      enqueue("focus_lost", { duration_ms: duration, reason: away.reason });
    };
    const onVisibility = () => (document.hidden ? markAway("tab_hidden") : markBack());
    const onBlur = () => markAway("window_blur");
    const onFocus = () => markBack();
    const onFullscreen = () => {
      if (document.fullscreenElement) {
        wasFullscreenRef.current = true;
        setFullscreenLost(false);
      } else if (wasFullscreenRef.current) {
        wasFullscreenRef.current = false;
        if (!startedRef.current) return; // the session has ended (submitted)
        if (pausedRef.current !== null) return; // leaving fullscreen during a declared break is fine
        setFullscreenLost(true);
        enqueue("fullscreen_exit");
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("fullscreenchange", onFullscreen);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("fullscreenchange", onFullscreen);
    };
  }, [enabled, started, enqueue]);

  // ---------- declared breaks (Pause button) ----------
  const pause = useCallback(
    ({ record }: { record: boolean }) => {
      if (pausedRef.current !== null) return;
      const now = Date.now();
      pausedRef.current = now;
      awayRef.current = null;
      setPausedSince(now);
      setFullscreenLost(false);
      if (record && startedRef.current) {
        enqueue("break_start");
        void flush();
      }
    },
    [enqueue, flush],
  );

  const resume = useCallback(
    async ({ record }: { record: boolean }) => {
      const since = pausedRef.current;
      if (since === null) return;
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen?.().catch(() => undefined);
      }
      wasFullscreenRef.current = !!document.fullscreenElement;
      pausedRef.current = null;
      awayRef.current = null;
      setPausedSince(null);
      if (record && startedRef.current) {
        enqueue("break_end", { duration_ms: Date.now() - since });
        void flush();
      }
    },
    [enqueue, flush],
  );

  // ---------- end of session (work handed in) ----------
  const end = useCallback(async () => {
    if (!startedRef.current) return;
    // stop recording first, so leaving the tab or fullscreen from here on isn't counted
    startedRef.current = false;
    wasFullscreenRef.current = false;
    awayRef.current = null;
    lastEditAtRef.current = null;
    pausedRef.current = null; // a break can't outlive the submission
    setPausedSince(null);
    setFullscreenLost(false);
    setStarted(false);
    await flush(); // the events + final typing stats reach the server before grading
  }, [flush]);

  // ---------- periodic + unload flush ----------
  useEffect(() => {
    if (!enabled || !started) return;
    const t = setInterval(() => void flush(), FLUSH_EVERY_MS);
    const onPageHide = () => void flush(true);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      clearInterval(t);
      window.removeEventListener("pagehide", onPageHide);
      void flush(true); // navigating away inside the app
    };
  }, [enabled, started, flush]);

  // leave fullscreen when the workspace unmounts
  useEffect(
    () => () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (startedRef.current && document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    },
    [],
  );

  return {
    enabled,
    sessionId: sessionIdRef.current,
    started,
    start,
    summary,
    toast,
    dismissToast: () => setToast(null),
    fullscreenLost,
    returnToFullscreen,
    recordBlocked,
    recordChange,
    recordKeystroke,
    flush: () => flush(false),
    suppressFocusTracking,
    paused: pausedSince !== null,
    pausedSince,
    pause,
    resume,
    end,
  };
}
