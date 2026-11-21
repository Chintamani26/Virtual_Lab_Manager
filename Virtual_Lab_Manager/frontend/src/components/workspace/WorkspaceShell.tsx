"use client";

import type { ReactNode } from "react";
import { cx } from "@/components/ui";
import type { MobilePane } from "./types";

/**
 * Full-height IDE frame: fixed header + stable dual-pane grid.
 * ≥ lg: editor | results side by side (fixed fractions, no reflow when results arrive).
 * < lg: a segmented control swaps panes instead of squeezing them.
 */
export function WorkspaceShell({
  header,
  left,
  right,
  overlays,
  mobilePane,
  onMobilePaneChange,
  resultsBadge,
}: {
  header: ReactNode;
  left: ReactNode;
  right: ReactNode;
  overlays?: ReactNode;
  mobilePane: MobilePane;
  onMobilePaneChange: (p: MobilePane) => void;
  resultsBadge?: ReactNode;
}) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas font-sans text-fg">
      {header}

      <div className="flex h-11 shrink-0 items-center border-b border-line bg-surface-1 px-3 lg:hidden">
        <div className="grid w-full grid-cols-2 rounded-lg border border-line bg-canvas p-0.5" role="tablist">
          {(
            [
              ["editor", "Editor"],
              ["results", "Results"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={mobilePane === id}
              onClick={() => onMobilePaneChange(id)}
              className={cx(
                "flex h-8 items-center justify-center gap-1.5 rounded-ctl text-xs font-medium transition duration-150",
                mobilePane === id ? "bg-surface-3 text-fg" : "text-fg-faint hover:text-fg-muted",
              )}
            >
              {label}
              {id === "results" && resultsBadge}
            </button>
          ))}
        </div>
      </div>

      <div className="relative grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.32fr)_minmax(0,1fr)]">
        <section
          className={cx(
            "min-h-0 min-w-0 flex-col bg-surface-1 lg:flex lg:border-r lg:border-line",
            mobilePane === "editor" ? "flex" : "hidden",
          )}
        >
          {left}
        </section>
        <section className={cx("min-h-0 min-w-0 flex-col bg-surface-1 lg:flex", mobilePane === "results" ? "flex" : "hidden")}>
          {right}
        </section>
        {overlays}
      </div>
    </div>
  );
}
