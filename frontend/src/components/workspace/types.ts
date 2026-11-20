export type RunKind = "run" | "test" | "submit";
export type SaveState = { state: "clean" | "dirty" | "saving" | "saved" | "error"; at: string | null };
export type MobilePane = "editor" | "results";

/** Imperative handle the code editor exposes (status-bar "jump to line"). */
export interface EditorHandle {
  reveal: (line: number, column: number) => void;
}
