"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { cx } from "@/components/ui";

interface SplitPaneResizeHandleProps {
  onResize: (newLeftPct: number) => void;
  onReset?: () => void;
  minPct?: number;
  maxPct?: number;
  className?: string;
}

/**
 * Draggable horizontal resize handle for the dual-pane IDE workspace.
 * Allows students to smoothly adjust editor vs. terminal width between minPct and maxPct.
 * Double-click resets to default. Supports keyboard left/right arrow navigation.
 */
export function SplitPaneResizeHandle({
  onResize,
  onReset,
  minPct = 28,
  maxPct = 76,
  className,
}: SplitPaneResizeHandleProps) {
  const [dragging, setDragging] = useState(false);
  const startXRef = useRef(0);
  const containerWidthRef = useRef(0);
  const initialLeftPctRef = useRef(56);

  useEffect(() => {
    if (!dragging) return;

    // Prevent text selection and Monaco cursor traps while dragging
    const prevUserSelect = document.body.style.userSelect;
    const prevCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    const onPointerMove = (e: PointerEvent) => {
      if (containerWidthRef.current <= 0) return;
      const deltaX = e.clientX - startXRef.current;
      const deltaPct = (deltaX / containerWidthRef.current) * 100;
      const nextPct = Math.min(maxPct, Math.max(minPct, initialLeftPctRef.current + deltaPct));
      onResize(Math.round(nextPct * 10) / 10);
    };

    const onPointerUp = () => {
      setDragging(false);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);

    return () => {
      document.body.style.userSelect = prevUserSelect;
      document.body.style.cursor = prevCursor;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [dragging, minPct, maxPct, onResize]);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const parent = e.currentTarget.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    containerWidthRef.current = rect.width;
    startXRef.current = e.clientX;
    const currentLeftWidth = e.currentTarget.offsetLeft;
    initialLeftPctRef.current = (currentLeftWidth / rect.width) * 100;
    setDragging(true);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const current = initialLeftPctRef.current || 56;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      const next = Math.max(minPct, current - 2);
      initialLeftPctRef.current = next;
      onResize(next);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = Math.min(maxPct, current + 2);
      initialLeftPctRef.current = next;
      onResize(next);
    } else if (e.key === "Home" && onReset) {
      e.preventDefault();
      initialLeftPctRef.current = 56;
      onReset();
    }
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label="Resize editor and results pane"
      aria-orientation="vertical"
      onPointerDown={onPointerDown}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      title="Drag to resize panes (double-click to reset)"
      className={cx(
        "group relative hidden lg:flex h-full w-2 shrink-0 cursor-col-resize select-none items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
        dragging ? "bg-indigo-500/20" : "hover:bg-indigo-500/10",
        className,
      )}
    >
      {/* 1px divider line */}
      <div
        className={cx(
          "h-full w-px transition-colors duration-150",
          dragging ? "bg-indigo-400" : "bg-line group-hover:bg-indigo-400/60",
        )}
      />

      {/* Grip handle bar */}
      <div
        className={cx(
          "absolute top-1/2 -translate-y-1/2 flex h-8 w-3 items-center justify-center rounded-sm transition-colors duration-150",
          dragging
            ? "bg-indigo-500 text-white shadow-glow-brand"
            : "bg-surface-3 text-fg-faint opacity-0 group-hover:opacity-100",
        )}
      >
        <svg width="4" height="12" viewBox="0 0 4 12" fill="currentColor">
          <circle cx="2" cy="2" r="1" />
          <circle cx="2" cy="6" r="1" />
          <circle cx="2" cy="10" r="1" />
        </svg>
      </div>
    </div>
  );
}
