// Helpers for the simplified nbformat-4 notebooks used by data.ipynb labs.

import type { CellOutput } from "./types";

export interface NbCell {
  cell_type: "markdown" | "code" | "raw";
  source: string | string[];
  metadata?: Record<string, unknown>;
  outputs?: unknown[];
  execution_count?: number | null;
  [k: string]: unknown;
}

export interface Notebook {
  nbformat?: number;
  nbformat_minor?: number;
  metadata?: Record<string, unknown>;
  cells: NbCell[];
  [k: string]: unknown;
}

export function sourceText(src: string | string[] | undefined): string {
  if (src === undefined) return "";
  return Array.isArray(src) ? src.join("") : src;
}

/** Split into nbformat-style line list (each line keeps its trailing "\n" except the last). */
function toLineList(text: string): string[] {
  if (!text) return [];
  const parts = text.split("\n");
  return parts.map((p, i) => (i < parts.length - 1 ? p + "\n" : p)).filter((p, i, arr) => !(i === arr.length - 1 && p === ""));
}

export function parseNotebook(raw: string): { nb: Notebook | null; error: string | null } {
  try {
    const parsed = JSON.parse(raw) as Partial<Notebook>;
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.cells)) {
      return { nb: null, error: "Notebook JSON has no `cells` array." };
    }
    return { nb: parsed as Notebook, error: null };
  } catch (e) {
    return { nb: null, error: e instanceof Error ? e.message : "Invalid notebook JSON" };
  }
}

/** Return a new serialized notebook with one cell's source replaced (preserving string vs list form). */
export function updateCellSource(nb: Notebook, index: number, text: string): string {
  const cells = nb.cells.map((c, i) => {
    if (i !== index) return c;
    return { ...c, source: Array.isArray(c.source) ? toLineList(text) : text };
  });
  return JSON.stringify({ ...nb, cells }, null, 1);
}

/**
 * Map backend cell outputs to notebook cell indices.
 * The contract's `CellOutput.index` may refer either to the position in `cells` (all cells)
 * or to the ordinal among code cells; detect which and normalise to the overall cell index.
 */
export function mapCellOutputs(nb: Notebook, outputs: CellOutput[] | null | undefined): Map<number, CellOutput> {
  const map = new Map<number, CellOutput>();
  if (!outputs || outputs.length === 0) return map;
  const codeIdx = nb.cells.map((c, i) => (c.cell_type === "code" ? i : -1)).filter((i) => i >= 0);
  const allPointToCode = outputs.every((o) => nb.cells[o.index]?.cell_type === "code");
  for (const o of outputs) {
    const overall = allPointToCode ? o.index : codeIdx[o.index];
    if (overall !== undefined) map.set(overall, o);
  }
  return map;
}
