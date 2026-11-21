"use client";

import { useMemo } from "react";
import { Markdown } from "@/components/Markdown";
import { cx } from "@/components/ui";
import { mapCellOutputs, parseNotebook, sourceText, updateCellSource } from "@/lib/notebook";
import type { CellOutput } from "@/lib/types";
import type { EditChange } from "@/lib/useProctoring";

export function NotebookEditor({
  value,
  onChange,
  cellOutputs,
  readOnly = false,
  dark = true,
  onRunAll,
  typing,
}: {
  value: string;
  onChange?: (v: string) => void;
  cellOutputs?: CellOutput[] | null;
  readOnly?: boolean;
  dark?: boolean;
  onRunAll?: () => void;
  /** proctoring telemetry (typed chars / keystrokes) — set only for proctored labs */
  typing?: { recordChange: (c: EditChange) => void; recordKeystroke: () => void };
}) {
  const { nb, error } = useMemo(() => parseNotebook(value), [value]);
  const outputs = useMemo(() => (nb ? mapCellOutputs(nb, cellOutputs) : new Map<number, CellOutput>()), [nb, cellOutputs]);

  if (!nb) {
    return (
      <div className={cx("flex h-full flex-col gap-2 p-4", dark ? "text-slate-300" : "text-slate-700")}>
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-400">
          Could not parse the notebook: {error}
        </div>
        <textarea
          className={cx(
            "flex-1 rounded-lg p-3 font-mono text-xs outline-none",
            dark ? "bg-slate-900 text-slate-200 ring-1 ring-slate-800" : "bg-white ring-1 ring-slate-200",
          )}
          value={value}
          readOnly={readOnly}
          onChange={(e) => onChange?.(e.target.value)}
          spellCheck={false}
        />
      </div>
    );
  }

  let codeCounter = 0;

  return (
    <div className={cx("h-full overflow-auto scroll-dark px-4 py-4", dark ? "bg-surface-1" : "bg-white")}>
      {onRunAll && !readOnly && (
        <div className="mb-3 flex justify-end">
          <button onClick={onRunAll} className="btn btn-secondary">
            Run all cells
          </button>
        </div>
      )}
      <div className="space-y-3">
        {nb.cells.map((cell, i) => {
          const text = sourceText(cell.source);
          if (cell.cell_type !== "code") {
            return (
              <div key={i} className={cx("rounded-lg px-4 py-3", dark ? "border border-line bg-surface-2/60" : "bg-slate-50")}>
                <Markdown dark={dark}>{text || "_(empty markdown cell)_"}</Markdown>
              </div>
            );
          }
          codeCounter += 1;
          const out = outputs.get(i);
          const rows = Math.max(2, text.split("\n").length);
          return (
            <div key={i} className="flex gap-2">
              <div className={cx("w-14 shrink-0 pt-2 text-right font-mono text-[11px]", dark ? "text-fg-faint" : "text-slate-400")}>
                In [{out ? codeCounter : " "}]:
              </div>
              <div className="min-w-0 flex-1">
                <textarea
                  value={text}
                  readOnly={readOnly}
                  rows={rows}
                  spellCheck={false}
                  onKeyDown={typing ? () => typing.recordKeystroke() : undefined}
                  onChange={(e) => {
                    if (typing) {
                      const delta = e.target.value.length - text.length;
                      typing.recordChange({ inserted: Math.max(0, delta), isFlush: false, isUndoRedo: false });
                    }
                    onChange?.(updateCellSource(nb, i, e.target.value));
                  }}
                  className={cx(
                    "block w-full resize-y rounded-lg px-3 py-2 font-mono text-[13px] leading-5 outline-none transition",
                    dark
                      ? "bg-surface-2 text-fg ring-1 ring-inset ring-line-strong focus:ring-2 focus:ring-brand/60"
                      : "bg-slate-50 text-slate-900 ring-1 ring-slate-200 focus:ring-indigo-400",
                  )}
                />
                {out && (out.stdout || out.error) && (
                  <div
                    className={cx(
                      "mt-1 rounded-lg px-3 py-2 font-mono text-xs whitespace-pre-wrap",
                      dark ? "bg-canvas text-fg-muted ring-1 ring-inset ring-line" : "bg-white text-slate-700 ring-1 ring-slate-200",
                    )}
                  >
                    {out.stdout}
                    {out.error && <div className="mt-1 text-rose-400">{out.error}</div>}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
