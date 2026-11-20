"use client";

/**
 * Exam lockdown for one lab page (docs/API.md v1.2).
 *
 * A browser cannot close a student's other tabs or apps, so the lockdown is enforced on the server.
 * The tab that starts the exam holds it, and everything else locks it until a mentor unlocks it:
 *   - leaving the window (tab hidden at once; window blur after a 1.5 s grace period)
 *   - exiting fullscreen
 *   - developer-tools shortcuts
 *   - opening the exam in a second tab (BroadcastChannel here; the server also enforces it)
 *   - closing, reloading or navigating away (keepalive request on pagehide / unmount)
 * Pause starts a declared break instead (limited in number and length by the server): nothing above counts while
 * paused, the work is hidden, and Resume re-enters fullscreen. A break that runs over the limit locks the exam.
 * Every enforced API call carries X-Exam-Session (and the SEB headers in Safe Exam Browser mode),
 * via the header provider registered with the API client.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, getStoredUser, registerExamHeaders } from "@/lib/api";
import { firebaseEnabled, subscribeExamLive } from "@/lib/firebase";
import type { ExamState, ExamViolationType, LockdownMode } from "@/lib/types";
import { isDevtoolsCombo, type Proctoring } from "@/lib/useProctoring";

/** Page-level Safe Exam Browser JavaScript API (SEB 3.x / macOS 3.x). */
interface SafeExamBrowserApi {
  version?: string;
  security?: {
    configKey?: string;
    browserExamKey?: string;
    updateKeys?: (callback: () => void) => void;
  };
}

declare global {
  interface Window {
    SafeExamBrowser?: SafeExamBrowserApi;
  }
}

type KeyboardLockApi = { lock?: (keyCodes?: string[]) => Promise<void>; unlock?: () => void };

export type ExamPhase =
  | "off" // not a lockdown lab (or still loading)
  | "seb_required" // must be opened in Safe Exam Browser
  | "gate" // rules + "Start exam"
  | "live" // this tab holds the exam
  | "paused" // on a declared break (Pause): Resume continues, in this or a new tab
  | "resume" // a mentor unlocked; resume in this tab
  | "locked" // waiting for a mentor
  | "elsewhere" // another tab/window holds the exam
  | "submitted"; // read-only

const LIVE_HEARTBEAT_MS = 5_000;
const WAIT_POLL_MS = 3_000;
const BLUR_GRACE_MS = 1_500;

/** Optimistic local copy of backend VIOLATION_REASONS (the server's reason replaces it). */
const LOCAL_REASON: Record<ExamViolationType, string> = {
  focus_lost: "Left the exam window (switched tab or app)",
  fullscreen_exit: "Exited fullscreen",
  devtools_blocked: "Tried to open developer tools",
  second_tab: "Opened the exam in a second tab or window",
  page_closed: "Left the exam page (closed, reloaded or navigated away)",
};

export interface ExamLockdown {
  enabled: boolean;
  mode: LockdownMode;
  state: ExamState | null;
  phase: ExamPhase;
  sebRequired: boolean;
  /** window.SafeExamBrowser exists (we are inside SEB) */
  sebDetected: boolean;
  sebVersion: string | null;
  /** SEB is running but the server rejected its Config Key hash */
  sebRejected: boolean;
  starting: boolean;
  startError: string | null;
  /** another tab currently holds this exam (shown as a warning on the gate) */
  heldElsewhere: boolean;
  /** start or resume the exam in this tab — call from a click (requests fullscreen) */
  enter: () => Promise<void>;
  /** declared breaks left (server-enforced) */
  breaksLeft: number;
  /** start a break from the live tab */
  pause: () => Promise<void>;
  /** end the break — call from a click (requests fullscreen) */
  resumeBreak: () => Promise<void>;
  pauseError: string | null;
  refresh: () => Promise<void>;
  /** map an enforced-call error (423 / 409 / 403) to exam state; true = handled, don't show a toast */
  handleError: (e: unknown) => boolean;
  /** true while the submission is being graded: the work is handed in, so leaving doesn't lock the exam */
  setHandingIn: (on: boolean) => void;
  markSubmitted: () => void;
}

function sebApi(): SafeExamBrowserApi | undefined {
  return typeof window !== "undefined" ? window.SafeExamBrowser : undefined;
}

/** Ask SEB to recompute its keys for the current URL (needed after client-side navigation). */
function refreshSebKeys(): Promise<void> {
  const sec = sebApi()?.security;
  if (!sec?.updateKeys) return Promise.resolve();
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        resolve();
      }
    };
    try {
      sec.updateKeys!(finish);
    } catch {
      finish();
    }
    setTimeout(finish, 1500);
  });
}

function keyboardApi(): KeyboardLockApi | undefined {
  if (typeof navigator === "undefined") return undefined;
  return (navigator as unknown as { keyboard?: KeyboardLockApi }).keyboard;
}

/** Optional: in fullscreen, route system keys (Esc, ⌘/Ctrl+W/T/N…) to the page. Chromium only. */
async function lockKeyboard() {
  try {
    if (document.fullscreenElement) await keyboardApi()?.lock?.();
  } catch {
    /* unsupported / denied — the lockdown does not depend on it */
  }
}

function unlockKeyboard() {
  try {
    keyboardApi()?.unlock?.();
  } catch {
    /* ignore */
  }
}

function phaseOf(
  enabled: boolean,
  s: ExamState | null,
  sebRequired: boolean,
  sebOk: boolean,
  claimed: boolean,
): ExamPhase {
  if (!enabled || !s) return "off";
  if (s.status === "submitted") return "submitted";
  if (s.status === "locked") return "locked";
  if (s.status === "paused") return "paused";
  if (sebRequired && !sebOk) return "seb_required";
  if (s.status === "not_started") return "gate";
  if (s.is_current_session) return "live";
  if (s.awaiting_resume) return "resume";
  return claimed ? "elsewhere" : "gate";
}

export function useExamLockdown({
  practicalId,
  lockdownMode,
  initial,
  proctoring,
}: {
  practicalId: string;
  lockdownMode: LockdownMode | undefined;
  initial: ExamState | null | undefined;
  proctoring: Proctoring;
}): ExamLockdown {
  const mode: LockdownMode = lockdownMode ?? "off";
  const enabled = mode !== "off" && !!initial;
  const sessionId = proctoring.sessionId;

  const [stateRaw, setState] = useState<ExamState | null>(initial ?? null);
  // before the seed effect runs, fall back to the server's initial state (no unguarded first frame)
  const state = stateRaw ?? initial ?? null;
  const [claimed, setClaimed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [sebDetected, setSebDetected] = useState(false);
  const [sebVersion, setSebVersion] = useState<string | null>(null);
  const [sebRejected, setSebRejected] = useState(false);
  const [pauseError, setPauseError] = useState<string | null>(null);

  const seededRef = useRef(false);
  const liveRef = useRef(false);
  const epochRef = useRef(0); // bumps on every local transition; stale responses are dropped
  const pendingRef = useRef<{ type: ExamViolationType; detail?: string } | null>(null);
  const startingRef = useRef(false);
  const handingInRef = useRef(false);
  const proctoringRef = useRef(proctoring);
  proctoringRef.current = proctoring;

  // seed from GET /student/practicals/{id} once it arrives
  useEffect(() => {
    if (initial && !seededRef.current) {
      seededRef.current = true;
      setState(initial);
    }
  }, [initial]);

  // detect Safe Exam Browser (client only)
  useEffect(() => {
    const seb = sebApi();
    setSebDetected(!!seb);
    setSebVersion(seb?.version ?? null);
    if (seb) void refreshSebKeys();
  }, []);

  const sebRequired = !!state?.seb_required || mode === "seb";
  const phase = phaseOf(enabled, state, sebRequired, sebDetected && !sebRejected, claimed);
  liveRef.current = phase === "live" && pendingRef.current === null;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  // every enforced call from this page carries the exam session (+ SEB proof)
  useEffect(() => {
    if (!enabled) return;
    registerExamHeaders(practicalId, () => {
      const h: Record<string, string> = { "X-Exam-Session": sessionId };
      const sec = sebApi()?.security;
      if (mode === "seb" && sec?.configKey) {
        h["X-SEB-Page-Url"] = window.location.href.split("#")[0];
        h["X-SEB-ConfigKey-Hash"] = sec.configKey;
      }
      return h;
    });
    return () => registerExamHeaders(practicalId, null);
  }, [enabled, practicalId, sessionId, mode]);

  const apply = useCallback((s: ExamState) => {
    setState(s);
    if (s.status !== "active") unlockKeyboard();
  }, []);

  const isSebError = (e: unknown) => e instanceof ApiError && e.status === 403 && /Safe Exam Browser/i.test(e.message);

  // ---------- violations ----------
  const sendPending = useCallback(
    async (keepalive: boolean) => {
      const v = pendingRef.current;
      if (!v) return;
      try {
        const s = await api.examViolation(
          practicalId,
          { session_id: sessionId, type: v.type, ...(v.detail ? { detail: v.detail.slice(0, 200) } : {}) },
          { keepalive },
        );
        if (pendingRef.current === v) pendingRef.current = null;
        if (!keepalive) apply(s);
      } catch {
        /* still pending: the poll loop retries, so a dropped request can't unlock the exam */
      }
    },
    [apply, practicalId, sessionId],
  );

  const report = useCallback(
    (type: ExamViolationType, detail?: string, keepalive = false) => {
      if (!liveRef.current || handingInRef.current) return;
      liveRef.current = false;
      epochRef.current += 1;
      pendingRef.current = { type, detail };
      unlockKeyboard();
      setState((s) =>
        s
          ? {
              ...s,
              status: "locked",
              lock_reason: LOCAL_REASON[type],
              locked_at: new Date().toISOString(),
              violations: s.violations + 1,
            }
          : s,
      );
      void sendPending(keepalive);
    },
    [sendPending],
  );
  const reportRef = useRef(report);
  reportRef.current = report;

  // ---------- heartbeat / waiting poll ----------
  const refresh = useCallback(async () => {
    if (!enabled) return;
    if (pendingRef.current) return sendPending(false);
    const epoch = epochRef.current;
    try {
      const s = await api.examHeartbeat(practicalId, sessionId);
      if (epoch === epochRef.current) apply(s);
    } catch (e) {
      if (isSebError(e)) setSebRejected(true);
    }
  }, [apply, enabled, practicalId, sendPending, sessionId]);

  const watching = enabled && phase !== "off" && phase !== "submitted" && phase !== "seb_required" && !(phase === "gate" && state?.status === "not_started");
  useEffect(() => {
    if (!watching) return;
    const t = setInterval(() => void refresh(), phase === "live" ? LIVE_HEARTBEAT_MS : WAIT_POLL_MS);
    return () => clearInterval(t);
  }, [watching, phase, refresh]);

  // ---------- Firebase real-time (optional): a mentor's lock / unlock reaches this screen instantly ----------
  // exam_live is a read-only mirror written by the API on status changes; any change → refresh now.
  // Polling above keeps running, so a failed / unavailable listener changes nothing.
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useEffect(() => {
    if (!enabled || !firebaseEnabled) return;
    const me = getStoredUser()?.id;
    if (!me) return;
    let last: string | null = null;
    return subscribeExamLive(practicalId, me, (doc) => {
      const sig = doc ? `${doc.status}|${doc.violations}|${doc.lock_reason ?? ""}` : "none";
      if (last !== null && sig !== last) void refreshRef.current();
      last = sig;
    });
  }, [enabled, practicalId]);

  // ---------- start / resume (must run inside a click: fullscreen needs a user gesture) ----------
  const enter = useCallback(async () => {
    if (!enabled || startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setStartError(null);
    try {
      const p = proctoringRef.current;
      if (!p.started) {
        await p.start(); // requests fullscreen first, then opens the proctoring session
      } else if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen?.().catch(() => undefined);
      }
      await lockKeyboard();
      if (mode === "seb") await refreshSebKeys();
      epochRef.current += 1;
      const s = await api.examStart(practicalId, sessionId);
      pendingRef.current = null;
      setClaimed(true);
      setSebRejected(false);
      apply(s);
    } catch (e) {
      if (isSebError(e)) {
        setSebRejected(true);
      } else {
        setStartError(e instanceof Error ? e.message : "Could not start the exam. Try again.");
      }
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }, [apply, enabled, mode, practicalId, sessionId]);

  const handleError = useCallback(
    (e: unknown): boolean => {
      if (!enabled || !(e instanceof ApiError)) return false;
      if (isSebError(e)) {
        setSebRejected(true);
        return true;
      }
      if (e.status === 423 || (e.status === 409 && /exam|another tab|submitted/i.test(e.message))) {
        liveRef.current = false;
        void refresh();
        return true;
      }
      return false;
    },
    [enabled, refresh],
  );

  // ---------- declared breaks (Pause button) ----------
  const pause = useCallback(async () => {
    if (!liveRef.current) return;
    // stop watching first: leaving right after pressing Pause must not lock the exam
    liveRef.current = false;
    epochRef.current += 1;
    setPauseError(null);
    unlockKeyboard();
    proctoringRef.current.pause({ record: false }); // the server records exam breaks
    const before = state;
    setState((s) => (s ? { ...s, status: "paused", paused_at: new Date().toISOString(), is_current_session: false } : s));
    try {
      apply(await api.examPause(practicalId, sessionId));
    } catch (e) {
      setPauseError(e instanceof Error ? e.message : "Could not start the break");
      if (before) setState(before);
      void proctoringRef.current.resume({ record: false });
      void refresh();
    }
  }, [apply, practicalId, refresh, sessionId, state]);

  const resumeBreak = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setStartError(null);
    try {
      const p = proctoringRef.current;
      await p.resume({ record: false }); // re-enters fullscreen (needs this click)
      if (!p.started) await p.start(); // page was reloaded during the break: open a new proctoring session
      await lockKeyboard();
      if (mode === "seb") await refreshSebKeys();
      epochRef.current += 1;
      const s = await api.examResume(practicalId, sessionId);
      setClaimed(true);
      apply(s);
    } catch (e) {
      if (isSebError(e)) setSebRejected(true);
      else setStartError(e instanceof Error ? e.message : "Could not resume. Try again.");
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }, [apply, mode, practicalId, sessionId]);

  // back from a break in this tab after a reload: the proctoring hook doesn't know it's a break
  useEffect(() => {
    if (phase === "paused" && !proctoringRef.current.paused) proctoringRef.current.pause({ record: false });
  }, [phase]);

  const setHandingIn = useCallback((on: boolean) => {
    handingInRef.current = on;
  }, []);

  const markSubmitted = useCallback(() => {
    liveRef.current = false;
    epochRef.current += 1;
    unlockKeyboard();
    setState((s) => (s ? { ...s, status: "submitted", is_current_session: false, awaiting_resume: false } : s));
  }, []);

  // ---------- violation detectors (only while this tab holds the exam) ----------
  useEffect(() => {
    if (phase !== "live") return;
    let blurTimer: ReturnType<typeof setTimeout> | null = null;
    let wasFullscreen = !!document.fullscreenElement;

    const onVisibility = () => {
      if (document.visibilityState === "hidden") reportRef.current("focus_lost", "tab_hidden");
    };
    const onBlur = () => {
      if (blurTimer) clearTimeout(blurTimer);
      blurTimer = setTimeout(() => {
        blurTimer = null;
        if (!document.hasFocus()) reportRef.current("focus_lost", "window_blur");
      }, BLUR_GRACE_MS);
    };
    const onFocus = () => {
      if (blurTimer) clearTimeout(blurTimer);
      blurTimer = null;
    };
    const onFullscreen = () => {
      if (document.fullscreenElement) {
        wasFullscreen = true;
        void lockKeyboard();
      } else if (wasFullscreen) {
        reportRef.current("fullscreen_exit");
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (isDevtoolsCombo(e)) reportRef.current("devtools_blocked", e.key);
    };

    if (document.visibilityState === "hidden") onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("fullscreenchange", onFullscreen);
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      if (blurTimer) clearTimeout(blurTimer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("fullscreenchange", onFullscreen);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [phase]);

  // closing / reloading the tab (keepalive so it survives unload)
  useEffect(() => {
    if (!enabled) return;
    const onPageHide = () => reportRef.current("page_closed", "page closed or reloaded", true);
    window.addEventListener("pagehide", onPageHide);
    return () => window.removeEventListener("pagehide", onPageHide);
  }, [enabled]);

  // navigating away inside the app (component unmount)
  useEffect(
    () => () => {
      if (liveRef.current) reportRef.current("page_closed", "navigated away from the exam", true);
      unlockKeyboard();
    },
    [],
  );

  // a second tab of this exam in the same browser: the tab holding it locks immediately
  const helloSentRef = useRef(false);
  useEffect(() => {
    if (!enabled || typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(`vlm-exam:${practicalId}`);
    ch.onmessage = (ev: MessageEvent<{ kind?: string; session?: string }>) => {
      if (ev.data?.kind === "hello" && ev.data.session !== sessionId && liveRef.current) {
        reportRef.current("second_tab", "another tab opened this exam");
      }
    };
    if (!helloSentRef.current) {
      helloSentRef.current = true;
      ch.postMessage({ kind: "hello", session: sessionId });
    }
    return () => ch.close();
  }, [enabled, practicalId, sessionId]);

  const heldElsewhere = !!state && state.status === "active" && !state.is_current_session && !state.awaiting_resume;
  const breaksLeft = Math.max(0, (state?.max_breaks ?? 0) - (state?.breaks_used ?? 0));

  return {
    enabled,
    mode,
    state,
    phase,
    sebRequired,
    sebDetected,
    sebVersion,
    sebRejected,
    starting,
    startError,
    heldElsewhere,
    enter,
    breaksLeft,
    pause,
    resumeBreak,
    pauseError,
    refresh,
    handleError,
    setHandingIn,
    markSubmitted,
  };
}
