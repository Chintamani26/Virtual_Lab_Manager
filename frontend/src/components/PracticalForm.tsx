"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { Markdown } from "./Markdown";
import { ExecutionSummary } from "./review";
import { TopicGenerator } from "./TopicGenerator";
import { Button, Card, CardHeader, Field, InlineError, SegmentedControl, cx, inputCls } from "./ui";
import { languageForFile } from "./workspace/CodeEditor";
import { api, LAB_FILE } from "@/lib/api";
import { parseNotebook, sourceText } from "@/lib/notebook";
import type {
  GeneratedPractical,
  Course,
  ExecutionResult,
  LabType,
  LockdownMode,
  Practical,
  PracticalInput,
  PracticalStatus,
  RubricCriterion,
  TestCaseSpec,
} from "@/lib/types";

const CodeEditor = dynamic(() => import("./workspace/CodeEditor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-400">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading editor…
    </div>
  ),
});

type FormTab = "basics" | "code" | "grading" | "proctoring";

const LOCKDOWN_OPTIONS: { value: LockdownMode; label: string; blurb: string }[] = [
  { value: "off", label: "Off", blurb: "Standard practice lab." },
  { value: "exam", label: "Strict exam", blurb: "Fullscreen, single tab. Leaving locks the session." },
  { value: "seb", label: "Safe Exam Browser", blurb: "Strict mode inside SEB. Requires a Config Key." },
];

const LAB_OPTIONS: { value: LabType; label: string; blurb: string }[] = [
  { value: "coding", label: "Coding", blurb: "Python + unit tests" },
  { value: "circuit", label: "Digital circuit", blurb: "Netlist + truth table" },
  { value: "notebook", label: "Data notebook", blurb: "Cells + assertions" },
];

const SEB_KEY_RE = /^[0-9a-fA-F]{64}$/;
const SEB_URL_RE = /^(https?|sebs?):\/\//;
const inputErrCls = inputCls
  .replace("border-slate-300", "border-rose-400")
  .replace("focus:border-indigo-500", "focus:border-rose-500")
  .replace("focus:ring-indigo-500/20", "focus:ring-rose-500/20");

/** Inline validation for the Safe Exam Browser fields (mirrors the backend PracticalInput validators). */
function sebErrors(input: PracticalInput): { key: string | null; url: string | null } {
  if (input.lockdown_mode !== "seb") return { key: null, url: null };
  const key = (input.seb_config_key ?? "").trim();
  const url = (input.seb_config_url ?? "").trim();
  return {
    key: !key
      ? "Required for Safe Exam Browser mode."
      : !SEB_KEY_RE.test(key)
        ? `Must be 64 hex characters (${key.length} entered).`
        : null,
    url: url && !SEB_URL_RE.test(url) ? "Must start with https://, http://, sebs:// or seb://" : null,
  };
}

/** Selectable option tile (lab type, lockdown mode). */
const optionCls = (active: boolean) =>
  cx(
    "flex flex-col justify-start rounded-lg border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60",
    active ? "border-indigo-600 ring-1 ring-indigo-600" : "border-slate-200 hover:border-slate-300",
  );

// ---------- helpers ----------
function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localInputToIso(v: string): string | null {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
}

function toInput(p: Practical): PracticalInput {
  return {
    course_id: p.course_id,
    title: p.title,
    description: p.description,
    lab_type: p.lab_type,
    starter_files: p.starter_files,
    test_cases: p.test_cases,
    rubric: p.rubric,
    max_score: p.max_score,
    due_at: p.due_at,
    status: p.status,
    proctored: p.proctored ?? true,
    lockdown_mode: p.lockdown_mode ?? "off",
    seb_config_key: p.seb_config_key ?? null,
    seb_config_url: p.seb_config_url ?? null,
  };
}

function defaultDue(): string {
  const d = new Date(Date.now() + 7 * 86_400_000);
  d.setHours(23, 59, 0, 0);
  return d.toISOString();
}

function primaryFile(input: PracticalInput): string {
  const preferred = LAB_FILE[input.lab_type];
  if (preferred in input.starter_files) return preferred;
  return Object.keys(input.starter_files)[0] ?? preferred;
}

/** Normalise tests/rubric before sending to the API. */
function cleanInput(input: PracticalInput, status: PracticalStatus): PracticalInput {
  const isCircuit = input.lab_type === "circuit";
  const seb = input.lockdown_mode === "seb";
  return {
    ...input,
    title: input.title.trim(),
    status,
    proctored: input.lockdown_mode !== "off" ? true : input.proctored,
    seb_config_key: seb ? (input.seb_config_key ?? "").trim().toLowerCase() || null : null,
    seb_config_url: seb ? (input.seb_config_url ?? "").trim() || null : null,
    test_cases: input.test_cases.map((t) => ({
      name: t.name.trim(),
      description: t.description,
      hidden: t.hidden,
      code: isCircuit ? null : (t.code ?? ""),
      inputs: isCircuit ? (t.inputs ?? {}) : null,
      expected: isCircuit ? (t.expected ?? {}) : null,
    })),
    rubric: input.rubric.map((r, i) => ({
      ...r,
      id: r.id?.trim() || slug(r.name) || `criterion_${i + 1}`,
      max_points: Number(r.max_points) || 0,
    })),
    max_score: Number(input.max_score) || 10,
  };
}

// ---------- component ----------
export function PracticalForm({ existing }: { existing?: Practical }) {
  const router = useRouter();
  const isEdit = !!existing;

  const [tab, setTab] = useState<FormTab>("basics");
  const [expandedTests, setExpandedTests] = useState<Set<number>>(() => new Set());
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [form, setForm] = useState<PracticalInput>(
    existing
      ? toInput(existing)
      : {
        course_id: "",
        title: "",
        description: "",
        lab_type: "coding",
        starter_files: {},
        test_cases: [],
        rubric: [],
        max_score: 10,
        due_at: defaultDue(),
        status: "draft",
        proctored: true,
        lockdown_mode: "off",
        seb_config_key: null,
        seb_config_url: null,
      },
  );
  const [showSebErrors, setShowSebErrors] = useState(false);
  const [descTab, setDescTab] = useState<"write" | "preview">("write");
  const [templateLoading, setTemplateLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [genMsg, setGenMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState<PracticalStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [refCode, setRefCode] = useState<string>("");
  const [validation, setValidation] = useState<ExecutionResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);

  const lastTemplateDesc = useRef<string | null>(null);

  useEffect(() => {
    api
      .facultyDashboard()
      .then((d) => {
        setCourses(d.courses);
        // ?course= (e.g. "Practice practical" from Where students struggle) preselects one of my courses
        const wanted = new URLSearchParams(window.location.search).get("course");
        const preferred = d.courses.some((c) => c.id === wanted) ? wanted! : d.courses[0]?.id ?? "";
        setForm((f) => (f.course_id ? f : { ...f, course_id: preferred }));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load courses"));
  }, []);

  useEffect(() => {
    if (!isEdit) void loadTemplate("coding", true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (existing) setRefCode(existing.starter_files[primaryFile(toInput(existing))] ?? "");
  }, [existing]);

  async function loadTemplate(labType: LabType, initial = false) {
    setTemplateLoading(true);
    setError(null);
    try {
      const t = await api.template(labType);
      setForm((f) => {
        const replaceDesc = !f.description.trim() || f.description === lastTemplateDesc.current;
        return {
          ...f,
          lab_type: labType,
          description: replaceDesc ? t.description : f.description,
          starter_files: t.starter_files,
          test_cases: t.test_cases,
          rubric: t.rubric,
        };
      });
      setExpandedTests(new Set());
      lastTemplateDesc.current = t.description;
      if (!initial) setGenMsg(`Loaded ${LAB_FILE[labType]} template.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load template");
    } finally {
      setTemplateLoading(false);
    }
  }

  function changeLabType(labType: LabType) {
    if (labType === form.lab_type) return;
    if (
      isEdit &&
      !window.confirm("Switching lab type replaces starter files, test cases, and rubric with the template. Continue?")
    )
      return;
    void loadTemplate(labType);
  }

  function set<K extends keyof PracticalInput>(key: K, value: PracticalInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function updateTest(i: number, patch: Partial<TestCaseSpec>) {
    setForm((f) => ({ ...f, test_cases: f.test_cases.map((t, j) => (j === i ? { ...t, ...patch } : t)) }));
  }

  function toggleTest(i: number) {
    setExpandedTests((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function addTest() {
    const idx = form.test_cases.length;
    const blank: TestCaseSpec =
      form.lab_type === "circuit"
        ? { name: `test_case_${idx + 1}`, description: "", hidden: false, inputs: {}, expected: {} }
        : { name: `test_case_${idx + 1}`, description: "", hidden: false, code: "assert True\n" };
    set("test_cases", [...form.test_cases, blank]);
    setExpandedTests((prev) => new Set(prev).add(idx));
  }

  function removeTest(i: number) {
    set("test_cases", form.test_cases.filter((_, j) => j !== i));
    setExpandedTests((prev) => {
      const next = new Set<number>();
      for (const idx of prev) {
        if (idx < i) next.add(idx);
        else if (idx > i) next.add(idx - 1);
      }
      return next;
    });
  }

  /** "Create from a topic": the generated practical replaces the form's content (still an unsaved draft). */
  function applyGenerated(g: GeneratedPractical) {
    setForm((f) => ({
      ...f,
      lab_type: "coding",
      title: g.title,
      description: g.description,
      starter_files: g.starter_files,
      test_cases: g.test_cases,
      rubric: g.rubric,
      max_score: g.max_score,
    }));
    lastTemplateDesc.current = null;
    setExpandedTests(new Set());
    setGenMsg(null);
  }

  function updateRubric(i: number, patch: Partial<RubricCriterion>) {
    setForm((f) => ({ ...f, rubric: f.rubric.map((r, j) => (j === i ? { ...r, ...patch } : r)) }));
  }

  async function generateTests() {
    setGenLoading(true);
    setGenMsg(null);
    setError(null);
    try {
      const file = primaryFile(form);
      let reference = form.starter_files[file] ?? "";
      if (form.lab_type === "notebook") {
        const { nb } = parseNotebook(reference);
        reference = nb
          ? nb.cells
            .filter((c) => c.cell_type === "code")
            .map((c) => sourceText(c.source))
            .join("\n\n")
          : "";
      }
      const res = await api.generateTests({
        title: form.title || "Untitled practical",
        description: form.description,
        lab_type: form.lab_type,
        reference_code: reference || undefined,
      });
      const existingNames = new Set(form.test_cases.map((t) => t.name));
      const startIndex = form.test_cases.length;
      const added = res.test_cases.map((t) => {
        let name = t.name;
        let k = 2;
        while (existingNames.has(name)) name = `${t.name}_${k++}`;
        existingNames.add(name);
        return { ...t, name };
      });
      set("test_cases", [...form.test_cases, ...added]);
      if (added.length > 0) setExpandedTests((prev) => new Set(prev).add(startIndex));
      setGenMsg(`Added ${added.length} test${added.length === 1 ? "" : "s"} (${res.source === "gemini" ? res.model : "offline"}).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test generation failed");
    } finally {
      setGenLoading(false);
    }
  }

  async function save(status: PracticalStatus) {
    setError(null);
    if (!form.course_id) {
      setTab("basics");
      return setError("Select a course.");
    }
    if (!form.title.trim()) {
      setTab("basics");
      return setError("Title is required.");
    }
    if (form.test_cases.some((t) => !t.name.trim())) {
      setTab("code");
      return setError("Every test case needs a name.");
    }
    if (status === "published" && form.test_cases.length === 0) {
      setTab("code");
      return setError("Add at least one test case before publishing.");
    }
    if (form.lab_type === "notebook") {
      const nbFile = form.starter_files["data.ipynb"];
      if (nbFile !== undefined && parseNotebook(nbFile).error) {
        setTab("code");
        return setError("data.ipynb is not valid notebook JSON.");
      }
    }
    const seb = sebErrors(form);
    if (seb.key || seb.url) {
      setShowSebErrors(true);
      setTab("proctoring");
      return setError("Fix the Safe Exam Browser settings before saving.");
    }
    setSaving(status);
    try {
      const body = cleanInput(form, status);
      if (isEdit && existing) await api.updatePractical(existing.id, body);
      else await api.createPractical(body);
      router.push("/faculty");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaving(null);
    }
  }

  async function validate() {
    if (!existing) return;
    setValidating(true);
    setValidateError(null);
    try {
      const file = primaryFile(form);
      const res = await api.validatePractical(existing.id, { ...form.starter_files, [file]: refCode });
      setValidation(res);
    } catch (e) {
      setValidateError(e instanceof Error ? e.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  const rubricTotal = useMemo(() => form.rubric.reduce((a, r) => a + (Number(r.max_points) || 0), 0), [form.rubric]);
  const hiddenCount = form.test_cases.filter((t) => t.hidden).length;
  const isCircuit = form.lab_type === "circuit";

  const tabs: { key: FormTab; label: string; meta?: string }[] = [
    { key: "basics", label: "Basics" },
    { key: "code", label: "Files & tests", meta: form.test_cases.length > 0 ? String(form.test_cases.length) : undefined },
    { key: "grading", label: "Grading", meta: form.rubric.length > 0 ? String(form.rubric.length) : undefined },
    {
      key: "proctoring",
      label: "Proctoring",
      meta: form.lockdown_mode !== "off" ? (form.lockdown_mode === "seb" ? "SEB" : "Exam") : undefined,
    },
  ];
  const tabIndex = tabs.findIndex((t) => t.key === tab);

  return (
    <div className="space-y-6">
      <div
        role="tablist"
        aria-label="Practical configuration sections"
        className="flex gap-1 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1"
      >
        {tabs.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.key)}
              className={cx(
                "flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-2 text-sm transition-colors",
                active ? "bg-slate-900 font-medium text-white" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
              )}
            >
              <span>{t.label}</span>
              {t.meta && (
                <span className={cx("text-xs tabular-nums", active ? "text-slate-300" : "text-slate-400")}>{t.meta}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Basics */}
      {tab === "basics" && (
        <div className="space-y-6">
          {!isEdit && form.lab_type === "coding" && <TopicGenerator courseId={form.course_id} onGenerated={applyGenerated} />}
          <Card>
            <CardHeader title="Details" />
            <div className="grid gap-5 p-5 md:grid-cols-2">
              <Field label="Course">
                <select
                  className={inputCls}
                  value={form.course_id}
                  onChange={(e) => set("course_id", e.target.value)}
                  disabled={!courses}
                >
                  {!courses && <option>Loading…</option>}
                  {courses?.length === 0 && <option value="">No courses assigned</option>}
                  {courses?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} · {c.title}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Title">
                <input
                  className={inputCls}
                  value={form.title}
                  placeholder="e.g. Lab 4: Binary Search Trees"
                  onChange={(e) => set("title", e.target.value)}
                />
              </Field>

              <div className="md:col-span-2">
                <span className="mb-1.5 block text-sm font-medium text-slate-700">Lab type</span>
                <div className="grid gap-3 sm:grid-cols-3">
                  {LAB_OPTIONS.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      aria-pressed={form.lab_type === o.value}
                      onClick={() => changeLabType(o.value)}
                      disabled={templateLoading}
                      className={optionCls(form.lab_type === o.value)}
                    >
                      <span className="flex items-baseline justify-between gap-2">
                        <span className="text-sm font-medium text-slate-900">{o.label}</span>
                        <span className="font-mono text-xs text-slate-400">{LAB_FILE[o.value]}</span>
                      </span>
                      <span className="mt-0.5 block text-xs text-slate-500">{o.blurb}</span>
                    </button>
                  ))}
                </div>
              </div>

              <Field label="Due date">
                <input
                  type="datetime-local"
                  className={inputCls}
                  value={isoToLocalInput(form.due_at)}
                  onChange={(e) => set("due_at", localInputToIso(e.target.value))}
                />
              </Field>
              <Field label="Max score">
                <input
                  type="number"
                  min={1}
                  step={1}
                  className={inputCls}
                  value={form.max_score}
                  onChange={(e) => set("max_score", Number(e.target.value))}
                />
              </Field>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Problem statement"
              subtitle="Markdown"
              action={
                <SegmentedControl
                  ariaLabel="Problem statement mode"
                  value={descTab}
                  onChange={setDescTab}
                  options={[
                    { value: "write", label: "Write" },
                    { value: "preview", label: "Preview" },
                  ]}
                />
              }
            />
            <div className="p-5">
              {descTab === "write" ? (
                <textarea
                  className={cx(inputCls, "min-h-56 font-mono text-[13px]")}
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                  placeholder="## Objective&#10;Describe the lab requirements…"
                />
              ) : (
                <div className="min-h-56 rounded-lg border border-slate-200 p-4">
                  <Markdown>{form.description || "_Nothing to preview._"}</Markdown>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Tab 2: Files & tests */}
      {tab === "code" && (
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Starter files"
              action={templateLoading ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : undefined}
            />
            <div className="space-y-4 p-5">
              {Object.keys(form.starter_files).length === 0 && (
                <p className="text-sm text-slate-500">Select a lab type in Basics to load starter files.</p>
              )}
              {Object.entries(form.starter_files).map(([name, content]) => (
                <div key={name}>
                  <p className="mb-1.5 font-mono text-xs text-slate-500">{name}</p>
                  {name.endsWith(".ipynb") ? (
                    <NotebookJsonField
                      value={content}
                      onChange={(v) => set("starter_files", { ...form.starter_files, [name]: v })}
                    />
                  ) : (
                    <div className="h-72 overflow-hidden rounded-lg border border-slate-200">
                      <CodeEditor
                        path={`form/${existing?.id ?? "new"}/${name}`}
                        value={content}
                        language={languageForFile(name)}
                        theme="light"
                        onChange={(v) => set("starter_files", { ...form.starter_files, [name]: v })}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Test cases"
              subtitle={
                form.test_cases.length > 0
                  ? `${form.test_cases.length} test${form.test_cases.length === 1 ? "" : "s"}${hiddenCount > 0 ? ` · ${hiddenCount} hidden` : ""}`
                  : isCircuit
                    ? "Input and expected output pairs"
                    : "Python assertions"
              }
              action={
                <div className="flex shrink-0 gap-2">
                  <Button type="button" size="sm" variant="secondary" loading={genLoading} onClick={generateTests}>
                    Generate with AI
                  </Button>
                  <Button type="button" size="sm" variant="secondary" onClick={addTest}>
                    Add test
                  </Button>
                </div>
              }
            />
            {genMsg && <p className="border-b border-slate-100 px-5 py-2.5 text-xs text-slate-600">{genMsg}</p>}
            {form.test_cases.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">No tests yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {form.test_cases.map((t, i) => {
                  const open = expandedTests.has(i);
                  return (
                    <li key={i} className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => toggleTest(i)}
                          aria-expanded={open}
                          className="flex min-w-0 flex-1 items-center gap-2 text-left"
                        >
                          {open ? (
                            <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                          ) : (
                            <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                          )}
                          <span className="truncate font-mono text-xs font-medium text-slate-900">
                            {t.name || "Untitled test"}
                          </span>
                          {t.description && <span className="hidden truncate text-xs text-slate-500 sm:inline">· {t.description}</span>}
                        </button>
                        <button
                          type="button"
                          aria-pressed={t.hidden}
                          onClick={() => updateTest(i, { hidden: !t.hidden })}
                          className={cx(
                            "h-7 rounded border px-2 text-xs font-medium transition-colors",
                            t.hidden
                              ? "border-slate-300 bg-slate-100 text-slate-900"
                              : "border-slate-200 bg-white text-slate-500 hover:text-slate-800",
                          )}
                          title="Hidden tests run only on submission"
                        >
                          {t.hidden ? "Hidden" : "Visible"}
                        </button>
                        <button
                          type="button"
                          onClick={() => removeTest(i)}
                          className="text-xs font-medium text-slate-400 hover:text-rose-700"
                        >
                          Remove
                        </button>
                      </div>

                      {open && (
                        <div className="mt-3 space-y-3 pl-6">
                          <div className="grid gap-3 sm:grid-cols-2">
                            <input
                              className={cx(inputCls, "font-mono text-xs")}
                              value={t.name}
                              aria-label="Test name"
                              onChange={(e) => updateTest(i, { name: e.target.value })}
                              placeholder="test_name"
                            />
                            <input
                              className={inputCls}
                              value={t.description}
                              aria-label="Test description"
                              onChange={(e) => updateTest(i, { description: e.target.value })}
                              placeholder="What this test checks"
                            />
                          </div>
                          {isCircuit ? (
                            <div className="grid gap-3 sm:grid-cols-2">
                              <JsonField
                                label="Inputs"
                                placeholder='{"A": 0, "B": 1}'
                                value={t.inputs ?? {}}
                                onChange={(v) => updateTest(i, { inputs: v })}
                              />
                              <JsonField
                                label="Expected outputs"
                                placeholder='{"SUM": 1, "CARRY": 0}'
                                value={t.expected ?? {}}
                                onChange={(v) => updateTest(i, { expected: v })}
                              />
                            </div>
                          ) : (
                            <textarea
                              className={cx(inputCls, "min-h-24 font-mono text-xs")}
                              value={t.code ?? ""}
                              spellCheck={false}
                              onChange={(e) => updateTest(i, { code: e.target.value })}
                              placeholder={"bst = BST()\nbst.insert(5)\nassert bst.search(5)"}
                              rows={Math.max(3, (t.code ?? "").split("\n").length)}
                            />
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      )}

      {/* Tab 3: Grading */}
      {tab === "grading" && (
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Rubric"
              subtitle={
                <span>
                  {rubricTotal} points total
                  {rubricTotal !== form.max_score && <span className="text-amber-700"> · scaled to {form.max_score}</span>}
                </span>
              }
              action={
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => set("rubric", [...form.rubric, { id: "", name: "", description: "", max_points: 2 }])}
                >
                  Add criterion
                </Button>
              }
            />
            <div className="space-y-3 p-5">
              {form.rubric.length === 0 && <p className="text-sm text-slate-500">No criteria yet.</p>}
              {form.rubric.length > 0 && (
                <div className="hidden gap-3 text-xs font-medium text-slate-500 sm:grid sm:grid-cols-[1fr_2fr_84px_64px]">
                  <span>Criterion</span>
                  <span>Full marks for</span>
                  <span>Points</span>
                </div>
              )}
              {form.rubric.map((r, i) => (
                <div key={i} className="grid items-start gap-3 sm:grid-cols-[1fr_2fr_84px_64px]">
                  <input
                    className={inputCls}
                    value={r.name}
                    aria-label="Criterion"
                    placeholder="Criterion"
                    onChange={(e) => updateRubric(i, { name: e.target.value })}
                  />
                  <input
                    className={inputCls}
                    value={r.description}
                    aria-label="What earns full marks"
                    placeholder="What earns full marks"
                    onChange={(e) => updateRubric(i, { description: e.target.value })}
                  />
                  <input
                    type="number"
                    min={0}
                    step={0.5}
                    className={inputCls}
                    aria-label="Points"
                    value={r.max_points}
                    onChange={(e) => updateRubric(i, { max_points: Number(e.target.value) })}
                  />
                  <button
                    type="button"
                    onClick={() => set("rubric", form.rubric.filter((_, j) => j !== i))}
                    className="h-9 rounded-md px-2 text-xs font-medium text-slate-400 hover:bg-slate-100 hover:text-rose-700"
                    title="Remove criterion"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </Card>

          {isEdit ? (
            <Card>
              <CardHeader
                title="Reference solution"
                subtitle={`Tests ${primaryFile(form)} against saved test cases`}
                action={
                  <Button type="button" size="sm" variant="secondary" loading={validating} onClick={validate}>
                    Validate
                  </Button>
                }
              />
              <div className="space-y-4 p-5">
                {form.lab_type === "notebook" ? (
                  <NotebookJsonField value={refCode} onChange={setRefCode} />
                ) : (
                  <div className="h-64 overflow-hidden rounded-lg border border-slate-200">
                    <CodeEditor
                      path={`validate/${existing?.id}/${primaryFile(form)}`}
                      value={refCode}
                      language={languageForFile(primaryFile(form))}
                      theme="light"
                      onChange={setRefCode}
                    />
                  </div>
                )}
                <InlineError message={validateError} />
                {validation && <ExecutionSummary result={validation} />}
              </div>
            </Card>
          ) : (
            <p className="text-xs text-slate-500">Save as a draft first to validate a reference solution.</p>
          )}
        </div>
      )}

      {/* Tab 4: Proctoring */}
      {tab === "proctoring" && (
        <Card>
          <CardHeader title="Proctoring" />
          <div className="p-5">
            <LockdownSettings form={form} set={set} showErrors={showSebErrors} />
          </div>
        </Card>
      )}

      {/* Action footer */}
      <div className="sticky bottom-0 z-10 -mx-4 border-t border-slate-200 bg-white px-4 py-3 sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1">
            {tabIndex > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setTab(tabs[tabIndex - 1].key)}>
                Back
              </Button>
            )}
            {tabIndex < tabs.length - 1 && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setTab(tabs[tabIndex + 1].key)}>
                Next: {tabs[tabIndex + 1].label}
              </Button>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <InlineError message={error} />
          </div>
          <Button type="button" variant="ghost" onClick={() => router.push("/faculty")}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="secondary"
            loading={saving === "draft"}
            disabled={saving !== null}
            onClick={() => save("draft")}
          >
            Save draft
          </Button>
          <Button
            type="button"
            loading={saving === "published"}
            disabled={saving !== null}
            onClick={() => save("published")}
          >
            {isEdit && existing?.status === "published" ? "Save changes" : "Publish"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------- exam lockdown (docs/API.md v1.2) ----------
function LockdownSettings({
  form,
  set,
  showErrors,
}: {
  form: PracticalInput;
  set: <K extends keyof PracticalInput>(key: K, value: PracticalInput[K]) => void;
  showErrors: boolean;
}) {
  const locked = form.lockdown_mode !== "off";
  const proctored = locked || form.proctored;
  const errs = sebErrors(form);
  const keyVal = form.seb_config_key ?? "";
  const keyErr = errs.key && (showErrors || keyVal.trim().length > 0) ? errs.key : null;
  const urlErr = errs.url;

  return (
    <div className="space-y-5" data-testid="lockdown-settings">
      <div className={cx("flex items-start gap-3", locked ? "cursor-not-allowed" : "cursor-pointer")}>
        <button
          type="button"
          role="switch"
          aria-checked={proctored}
          aria-label="Proctored session"
          disabled={locked}
          onClick={() => set("proctored", !form.proctored)}
          className={cx(
            "relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition disabled:opacity-60",
            proctored ? "bg-indigo-600" : "bg-slate-300",
          )}
        >
          <span
            className={cx(
              "inline-block h-4 w-4 transform rounded-full bg-white shadow transition",
              proctored ? "translate-x-4" : "translate-x-0.5",
            )}
          />
        </button>
        <span onClick={() => !locked && set("proctored", !form.proctored)}>
          <span className="block text-sm font-medium text-slate-900">
            Proctored session
            {locked && <span className="ml-2 text-xs font-normal text-slate-500">Required in exam mode</span>}
          </span>
          <span className="block text-xs text-slate-500">
            Disables copy, paste, and right-click, and logs focus and typing telemetry.
          </span>
        </span>
      </div>

      <div>
        <span className="mb-1.5 block text-sm font-medium text-slate-700">Exam lockdown</span>
        <div className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Exam lockdown">
          {LOCKDOWN_OPTIONS.map((o) => {
            const active = form.lockdown_mode === o.value;
            return (
              <button
                key={o.value}
                type="button"
                role="radio"
                aria-checked={active}
                data-testid={`lockdown-${o.value}`}
                onClick={() => {
                  set("lockdown_mode", o.value);
                  if (o.value !== "off") set("proctored", true);
                }}
                className={optionCls(active)}
              >
                <span className="block text-sm font-medium text-slate-900">{o.label}</span>
                <span className="mt-0.5 block text-xs text-slate-500">{o.blurb}</span>
              </button>
            );
          })}
        </div>
        {locked && (
          <p className="mt-2 text-xs text-slate-500">
            Locked students appear in the Live monitor and alerts bell until unlocked by faculty or HOD.
          </p>
        )}
      </div>

      {form.lockdown_mode === "seb" && (
        <div className="grid gap-4 border-t border-slate-100 pt-5 md:grid-cols-2" data-testid="seb-settings">
          <Field
            label="SEB Config Key"
            hint={
              keyErr ? (
                <span className="text-rose-600" data-testid="seb-key-error">
                  {keyErr}
                </span>
              ) : (
                "64-character hex key from SEB Config Tool."
              )
            }
          >
            <input
              className={cx(keyErr ? inputErrCls : inputCls, "font-mono text-xs leading-5")}
              value={keyVal}
              spellCheck={false}
              autoComplete="off"
              placeholder="64 hex characters"
              aria-invalid={!!keyErr}
              data-testid="seb-key-input"
              onChange={(e) => set("seb_config_key", e.target.value)}
            />
          </Field>
          <Field
            label="SEB config URL (optional)"
            hint={
              urlErr ? (
                <span className="text-rose-600" data-testid="seb-url-error">
                  {urlErr}
                </span>
              ) : (
                "Hosted .seb file URL for one-click launch."
              )
            }
          >
            <input
              className={urlErr ? inputErrCls : inputCls}
              value={form.seb_config_url ?? ""}
              placeholder="https://exams.example.edu/lab4.seb"
              aria-invalid={!!urlErr}
              data-testid="seb-url-input"
              onChange={(e) => set("seb_config_url", e.target.value)}
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function JsonField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: Record<string, number>;
  onChange: (v: Record<string, number>) => void;
  placeholder?: string;
}) {
  const valueStr = JSON.stringify(value);
  const [text, setText] = useState(valueStr);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    setText((current) => {
      try {
        if (JSON.stringify(JSON.parse(current)) === valueStr) return current;
      } catch {
        /* replace unparseable text */
      }
      setInvalid(false);
      return valueStr;
    });
  }, [valueStr]);

  function handle(v: string) {
    setText(v);
    try {
      const parsed = JSON.parse(v) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
      const out: Record<string, number> = {};
      for (const [k, val] of Object.entries(parsed as Record<string, unknown>)) {
        const n = Number(val);
        if (Number.isNaN(n)) throw new Error("non-numeric");
        out[k] = n;
      }
      setInvalid(false);
      onChange(out);
    } catch {
      setInvalid(true);
    }
  }

  return (
    <Field label={label} hint={invalid ? <span className="text-rose-600">Enter a JSON object of 0/1 values</span> : undefined}>
      <input
        className={cx(inputCls, "font-mono text-xs", invalid && "border-rose-400 focus:border-rose-500 focus:ring-rose-500/20")}
        value={text}
        placeholder={placeholder}
        onChange={(e) => handle(e.target.value)}
      />
    </Field>
  );
}

function NotebookJsonField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { nb, error } = useMemo(() => parseNotebook(value), [value]);
  return (
    <div>
      <textarea
        className={cx(inputCls, "min-h-72 font-mono text-xs", error && value && "border-rose-400")}
        value={value}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className={cx("mt-1 text-xs", error ? "text-rose-600" : "text-slate-500")}>
        {error
          ? `Invalid notebook JSON: ${error}`
          : `nbformat ${nb?.nbformat ?? 4} · ${nb?.cells.length ?? 0} cells (${nb?.cells.filter((c) => c.cell_type === "code").length ?? 0} code)`}
      </p>
    </div>
  );
}
