"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { PageContainer } from "@/components/AppShell";
import { downloadText, slugify } from "@/components/insights";
import { Markdown } from "@/components/Markdown";
import { VivaVoicePanel } from "@/components/VivaVoicePanel";
import { Button, Card, CardHeader, Field, InlineError, LinkButton, PageHeader, SegmentedControl, Skeleton, inputCls } from "@/components/ui";
import { api } from "@/lib/api";
import type { Course, Difficulty, TeachingMaterial } from "@/lib/types";

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
] as const;

function List({ title, items, ordered = false }: { title: string; items: string[]; ordered?: boolean }) {
  if (items.length === 0) return null;
  const Tag = ordered ? "ol" : "ul";
  return (
    <section>
      <h2 className="mb-2 text-base font-semibold text-slate-900">{title}</h2>
      <Tag className={`${ordered ? "list-decimal" : "list-disc"} space-y-1 pl-5 text-sm text-slate-700`}>
        {items.map((x, i) => <li key={i}>{x}</li>)}
      </Tag>
    </section>
  );
}

export default function TeachingMaterialPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [topic, setTopic] = useState("");
  const [courseId, setCourseId] = useState("");
  const [level, setLevel] = useState<Difficulty>("intermediate");
  const [notes, setNotes] = useState("");
  const [material, setMaterial] = useState<TeachingMaterial | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("topic");
    if (t) setTopic(t);
    api
      .facultyDashboard()
      .then((d) => setCourses(d.courses))
      .catch((err) => {
        if (process.env.NODE_ENV !== "production") console.warn("Failed to load courses:", err);
      });
  }, []);

  async function generate(e: FormEvent) {
    e.preventDefault();
    if (topic.trim().length < 3) return setError("Enter a topic of at least 3 characters.");
    setLoading(true);
    setError(null);
    try {
      setMaterial(await api.teachingMaterial({ topic: topic.trim(), level, course_id: courseId || undefined, notes: notes.trim() || undefined }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageContainer>
      <div className="mx-auto max-w-4xl">
        <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1.5 text-sm text-slate-500">
          <Link href="/faculty" className="hover:text-slate-900">
            Dashboard
          </Link>
          <span aria-hidden>/</span>
          <span className="text-slate-700">Teaching material</span>
        </nav>
        <PageHeader title="Teaching material" subtitle="Lecture notes, worked examples and viva questions for a topic, drafted by Gemini for you to review." />

        <Card>
          <form onSubmit={generate} className="grid gap-5 p-5 md:grid-cols-2">
            <div className="md:col-span-2">
              <Field label="Topic">
                <input className={inputCls} value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={200}
                  placeholder="e.g. Deadlock in operating systems" data-testid="teaching-topic" />
              </Field>
            </div>
            <Field label="Course (optional)">
              <select className={inputCls} value={courseId} onChange={(e) => setCourseId(e.target.value)}>
                <option value="">Any course</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} · {c.title}
                  </option>
                ))}
              </select>
            </Field>
            <div>
              <span className="mb-1.5 block text-sm font-medium text-slate-700">Student level</span>
              <SegmentedControl options={LEVELS} value={level} onChange={setLevel} ariaLabel="Student level" />
            </div>
            <div className="md:col-span-2">
              <Field label="Notes (optional)">
                <input className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000}
                  placeholder="e.g. focus on Banker's algorithm, include a resource-allocation example" />
              </Field>
            </div>
            <div className="flex items-center gap-3 md:col-span-2">
              <Button type="submit" loading={loading} data-testid="teaching-generate">
                {material ? "Generate again" : "Generate material"}
              </Button>
              {loading && <span className="text-sm text-slate-500">This takes about 20 seconds.</span>}
            </div>
            <div className="md:col-span-2">
              <InlineError message={error} />
            </div>
          </form>
        </Card>

        {loading && !material && (
          <div aria-hidden className="mt-6">
            <Card className="space-y-3 p-5">
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-11/12" />
              <Skeleton className="h-3 w-4/5" />
            </Card>
          </div>
        )}

        {material && (
          <div className="mt-6" data-testid="teaching-material">
          <Card>
            <CardHeader
              title={material.title}
              subtitle={`Draft by Gemini · ${material.model} · review before you teach from it`}
              action={
                <>
                  <LinkButton size="sm" variant="ghost" href={`/faculty/practicals/new?topic=${encodeURIComponent(topic)}${courseId ? `&course=${courseId}` : ""}`}>
                    Create a practical
                  </LinkButton>
                  <Button size="sm" variant="secondary" onClick={() => downloadText(`${slugify(material.title)}.md`, material.markdown)}>
                    Download
                  </Button>
                </>
              }
            />
            <div className="space-y-7 px-5 py-5">
              <p className="text-sm text-slate-700">{material.overview}</p>
              <List title="Learning outcomes" items={material.learning_outcomes} />
              {material.sections.map((s, i) => (
                <section key={i}>
                  <h2 className="mb-2 text-base font-semibold text-slate-900">{s.heading}</h2>
                  <Markdown>{s.content}</Markdown>
                </section>
              ))}
              {material.examples.length > 0 && (
                <section>
                  <h2 className="mb-2 text-base font-semibold text-slate-900">Worked examples</h2>
                  <div className="space-y-4">
                    {material.examples.map((ex, i) => (
                      <div key={i} className="rounded-md border border-slate-200 px-4 py-3">
                        <p className="mb-1 text-sm font-medium text-slate-900">{ex.heading}</p>
                        <Markdown>{ex.content}</Markdown>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              <List title="Real-world applications" items={material.real_world_examples} />
              <List title="Common mistakes" items={material.common_mistakes} />
              <List title="Discussion questions" items={material.discussion_questions} ordered />
              {material.viva_questions.length > 0 && (
                <VivaVoicePanel questions={material.viva_questions} topic={material.title} />
              )}
            </div>
          </Card>
          </div>
        )}
      </div>
    </PageContainer>
  );
}
