"use client";

import { useEffect, useRef } from "react";
import Editor, { type BeforeMount, type Monaco, type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { Loader2 } from "lucide-react";
import type { LintDiagnostic } from "@/lib/types";
import type { BlockedType, EditChange } from "@/lib/useProctoring";
import type { EditorHandle } from "./types";

/** Subset of the proctoring hook the editor needs (see src/lib/useProctoring.ts). */
export interface EditorProctoring {
  recordChange: (c: EditChange) => void;
  recordKeystroke: () => void;
  recordBlocked: (type: BlockedType) => void;
}

export type EditorLanguage = "python" | "circuit" | "json" | "plaintext" | "markdown";

/** Workspace theme matching the design tokens (surface-1 background, brand cursor). */
function defineWorkspaceTheme(monaco: Parameters<BeforeMount>[0]) {
  monaco.editor.defineTheme("vlm-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "6b7280", fontStyle: "italic" },
      { token: "keyword", foreground: "a78bfa" },
      { token: "string", foreground: "86efac" },
      { token: "number", foreground: "fbbf24" },
      { token: "type", foreground: "7dd3fc" },
      { token: "delimiter", foreground: "9aa3b2" },
    ],
    colors: {
      "editor.background": "#0f1117",
      "editorGutter.background": "#0f1117",
      "editor.lineHighlightBackground": "#151821",
      "editor.lineHighlightBorder": "#00000000",
      "editorLineNumber.foreground": "#3f4656",
      "editorLineNumber.activeForeground": "#9aa3b2",
      "editorCursor.foreground": "#818cf8",
      "editor.selectionBackground": "#6366f140",
      "editor.inactiveSelectionBackground": "#6366f126",
      "editorIndentGuide.background1": "#1c202b",
      "editorIndentGuide.activeBackground1": "#2a3040",
      "editorWidget.background": "#151821",
      "editorWidget.border": "#ffffff1a",
      "editorHoverWidget.background": "#151821",
      "editorHoverWidget.border": "#ffffff1a",
      "scrollbarSlider.background": "#ffffff14",
      "scrollbarSlider.hoverBackground": "#ffffff24",
    },
  });
}

/** Registers the circuit.sim netlist language + workspace theme once per Monaco instance. */
const registerCircuitLanguage: BeforeMount = (monaco) => {
  defineWorkspaceTheme(monaco);
  if (monaco.languages.getLanguages().some((l: { id: string }) => l.id === "circuit")) return;
  monaco.languages.register({ id: "circuit", extensions: [".sim"] });
  monaco.languages.setMonarchTokensProvider("circuit", {
    tokenizer: {
      root: [
        [/#.*$/, "comment"],
        [/\b(INPUT|OUTPUT)\b/, "keyword"],
        [/\b(AND|OR|NOT|XOR|NAND|NOR|XNOR|BUF)\b/, "type"],
        [/\b[01]\b/, "number"],
        [/[A-Za-z_]\w*/, "identifier"],
        [/[=(),]/, "delimiter"],
      ],
    },
  });
  monaco.languages.setLanguageConfiguration("circuit", {
    comments: { lineComment: "#" },
    brackets: [["(", ")"]],
    autoClosingPairs: [{ open: "(", close: ")" }],
  });
};

export function CodeEditor({
  path,
  value,
  onChange,
  language,
  readOnly = false,
  diagnostics,
  theme = "vs-dark",
  height = "100%",
  proctoring,
  onReady,
}: {
  path: string;
  value: string;
  onChange?: (v: string) => void;
  language: EditorLanguage;
  readOnly?: boolean;
  diagnostics?: LintDiagnostic[];
  theme?: "vs-dark" | "light";
  height?: string | number;
  /** when set, the editor runs in proctored mode (clipboard/drag-drop/context menu disabled + telemetry) */
  proctoring?: EditorProctoring;
  /** receives an imperative handle (jump to line) once Monaco is mounted */
  onReady?: (handle: EditorHandle) => void;
}) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  // latest callbacks without re-binding Monaco listeners
  const proctorRef = useRef(proctoring);
  proctorRef.current = proctoring;
  const proctored = !!proctoring;

  const onMount: OnMount = (ed, monaco) => {
    editorRef.current = ed;
    monacoRef.current = monaco;
    applyMarkers();
    // next/font loads JetBrains Mono asynchronously — re-measure glyphs once it is ready
    void document.fonts?.ready.then(() => monaco.editor.remeasureFonts());
    onReady?.({
      reveal: (line, column) => {
        ed.revealLineInCenter(line);
        ed.setPosition({ lineNumber: line, column: Math.max(1, column) });
        ed.focus();
      },
    });
    if (proctored) {
      const { KeyMod, KeyCode } = monaco;
      // Keyboard clipboard shortcuts are swallowed by Monaco commands (no native event fires).
      ed.addCommand(KeyMod.CtrlCmd | KeyCode.KeyV, () => proctorRef.current?.recordBlocked("paste_blocked"));
      ed.addCommand(KeyMod.CtrlCmd | KeyMod.Shift | KeyCode.KeyV, () => proctorRef.current?.recordBlocked("paste_blocked"));
      ed.addCommand(KeyMod.Shift | KeyCode.Insert, () => proctorRef.current?.recordBlocked("paste_blocked"));
      ed.addCommand(KeyMod.CtrlCmd | KeyCode.KeyC, () => proctorRef.current?.recordBlocked("copy_blocked"));
      ed.addCommand(KeyMod.CtrlCmd | KeyCode.Insert, () => proctorRef.current?.recordBlocked("copy_blocked"));
      ed.addCommand(KeyMod.CtrlCmd | KeyCode.KeyX, () => proctorRef.current?.recordBlocked("cut_blocked"));
      ed.addCommand(KeyMod.Shift | KeyCode.Delete, () => proctorRef.current?.recordBlocked("cut_blocked"));

      ed.onDidChangeModelContent((e) => {
        const p = proctorRef.current;
        if (!p) return;
        for (const c of e.changes) {
          p.recordChange({ inserted: c.text.length, isFlush: e.isFlush, isUndoRedo: e.isUndoing || e.isRedoing });
        }
      });
      ed.onKeyDown(() => proctorRef.current?.recordKeystroke());
      // Safety net: if a paste ever slips past the document-level guards, revert it.
      ed.onDidPaste(() => {
        ed.trigger("proctoring", "undo", null);
        proctorRef.current?.recordBlocked("paste_blocked");
      });
    }
  };

  function applyMarkers() {
    const ed = editorRef.current;
    const monaco = monacoRef.current;
    if (!ed || !monaco) return;
    const model = ed.getModel();
    if (!model) return;
    const lineCount = model.getLineCount();
    const markers: editor.IMarkerData[] = (diagnostics ?? []).map((d) => {
      const line = Math.min(Math.max(1, d.line || 1), lineCount);
      const maxCol = model.getLineMaxColumn(line);
      const col = Math.min(Math.max(1, d.column || 1), maxCol);
      return {
        startLineNumber: line,
        startColumn: col,
        endLineNumber: line,
        endColumn: col < maxCol ? maxCol : col + 1,
        message: `${d.message} (${d.source})`,
        severity:
          d.severity === "error"
            ? monaco.MarkerSeverity.Error
            : d.severity === "warning"
              ? monaco.MarkerSeverity.Warning
              : monaco.MarkerSeverity.Info,
      };
    });
    monaco.editor.setModelMarkers(model, "vlm-lint", markers);
  }

  // re-apply when diagnostics or the active model change
  useEffect(() => {
    applyMarkers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagnostics, path]);

  return (
    <Editor
      path={path}
      height={height}
      language={language}
      value={value}
      theme={theme === "vs-dark" ? "vlm-dark" : theme}
      beforeMount={registerCircuitLanguage}
      onMount={onMount}
      onChange={(v) => onChange?.(v ?? "")}
      loading={
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading editor…
        </div>
      }
      options={{
        readOnly,
        fontSize: 13.5,
        fontFamily: monoFontFamily(),
        fontLigatures: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: language === "python" ? 4 : 2,
        renderLineHighlight: "all",
        smoothScrolling: true,
        padding: { top: 12, bottom: 12 },
        wordWrap: language === "markdown" ? "on" : "off",
        lineNumbersMinChars: 3,
        fixedOverflowWidgets: true,
        ...(proctored
          ? {
              contextmenu: false,
              dragAndDrop: false,
              dropIntoEditor: { enabled: false },
              pasteAs: { enabled: false },
            }
          : {}),
      }}
    />
  );
}

export function languageForFile(filename: string): EditorLanguage {
  if (filename.endsWith(".py")) return "python";
  if (filename.endsWith(".sim")) return "circuit";
  if (filename.endsWith(".ipynb") || filename.endsWith(".json")) return "json";
  if (filename.endsWith(".md")) return "markdown";
  return "plaintext";
}

/** Resolve the next/font JetBrains Mono family (hashed name) for Monaco, with safe fallbacks. */
function monoFontFamily(): string {
  const fallback = '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace';
  if (typeof window === "undefined") return fallback;
  const fam = getComputedStyle(document.documentElement).getPropertyValue("--font-jetbrains").trim();
  return fam ? `${fam}, ${fallback}` : fallback;
}
