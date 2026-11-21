"use client";

import { useEffect, useRef } from "react";

/**
 * Calls `fn` now and every `ms` while this tab is visible. A hidden tab doesn't poll (each poll costs
 * database reads, and a forgotten background tab would otherwise poll all day); it refreshes as soon
 * as the tab is shown again.
 */
export function useVisiblePolling(fn: () => void, ms: number) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const startPolling = () => {
      stop();
      fnRef.current();
      timer = setInterval(() => fnRef.current(), ms);
    };
    const onVisibility = () => (document.hidden ? stop() : startPolling());

    if (document.hidden) fnRef.current(); // still load once, so the page isn't empty when shown
    else startPolling();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [ms]);
}
