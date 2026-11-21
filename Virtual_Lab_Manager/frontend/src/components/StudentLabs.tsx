"use client";

import Link from "next/link";
import { fmtDate, fmtScore, relativeDue } from "@/lib/api";
import type { Course, StudentPracticalSummary } from "@/lib/types";
import { Card, CardHeader, EmptyState, LinkButton, ScoreBar, cx, underlineTabCls } from "./ui";

/*
 * Building blocks shared by the student dashboard (/student) and the per-course pages (/student/courses/[id]).
 * Every list is split the same way: labs still to do on the left, completed labs (score + feedback) on the right.
 */

export function isDone(p: StudentPracticalSummary): boolean {
  return p.progress === "submitted" || p.progress === "graded";
}

/** To do: overdue first, then nearest deadline (no deadline last). Completed: most recent submission first. */
export function splitLabs(labs: StudentPracticalSummary[]) {
  const due = (p: StudentPracticalSummary) => (p.due_at ? new Date(p.due_at).getTime() : Number.POSITIVE_INFINITY);
  const submitted = (p: StudentPracticalSummary) => (p.submitted_at ? new Date(p.submitted_at).getTime() : 0);
  return {
    todo: labs.filter((p) => !isDone(p)).sort((a, b) => due(a) - due(b)),
    done: labs.filter(isDone).sort((a, b) => submitted(b) - submitted(a)),
  };
}

/** The two-column body of both pages; stacks to To do above Completed on small screens. */
export function LabColumns({ labs, showCourse }: { labs: StudentPracticalSummary[]; showCourse: boolean }) {
  const { todo, done } = splitLabs(labs);
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="To do" action={<Count n={todo.length} />} />
        {todo.length === 0 ? (
          <EmptyState title="Nothing pending. All labs are submitted." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {todo.map((p) => (
              <TodoRow key={p.id} p={p} showCourse={showCourse} />
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader title="Completed" action={<Count n={done.length} />} />
        {done.length === 0 ? (
          <EmptyState title="No completed labs yet." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {done.map((p) => (
              <CompletedRow key={p.id} p={p} showCourse={showCourse} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Count({ n }: { n: number }) {
  return <span className="text-sm tabular-nums text-slate-500">{n}</span>;
}

function TodoRow({ p, showCourse }: { p: StudentPracticalSummary; showCourse: boolean }) {
  const due = relativeDue(p.due_at);
  const started = p.progress === "in_progress";
  return (
    <li className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-slate-50/60">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{p.title}</p>
        <p className="mt-1 text-xs text-slate-500">
          {showCourse && `${p.course_code} · `}
          <span
            className={cx(
              due.tone === "late" && "font-medium text-rose-700",
              due.tone === "soon" && "font-medium text-amber-700",
            )}
          >
            {due.label}
          </span>
          {started && " · In progress"}
        </p>
      </div>
      <LinkButton href={`/student/labs/${p.id}`} variant={started ? "primary" : "secondary"} size="sm">
        {started ? "Continue" : "Start"}
      </LinkButton>
    </li>
  );
}

function CompletedRow({ p, showCourse }: { p: StudentPracticalSummary; showCourse: boolean }) {
  const graded = p.progress === "graded" && p.best_score !== null;
  const meta = [
    showCourse ? p.course_code : null,
    p.tests_total ? `${p.tests_passed}/${p.tests_total} tests` : null,
    p.submitted_at ? `Submitted ${fmtDate(p.submitted_at)}` : null,
    p.reviewed ? "Reviewed by faculty" : null,
  ].filter(Boolean);
  return (
    <li className="px-5 py-4 transition-colors hover:bg-slate-50/60">
      <div className="flex items-baseline justify-between gap-3">
        <Link
          href={`/student/labs/${p.id}`}
          className="min-w-0 truncate text-sm font-medium text-slate-900 hover:text-indigo-700"
        >
          {p.title}
        </Link>
        <span className="shrink-0 text-sm font-semibold tabular-nums text-slate-900">
          {graded ? fmtScore(p.best_score, p.max_score) : <span className="font-normal text-slate-500">Grading</span>}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{meta.join(" · ")}</p>
      {p.feedback && <p className="mt-2 line-clamp-2 text-sm text-slate-600">{p.feedback}</p>}
    </li>
  );
}

/** Course summary on the dashboard; the whole card opens the course page. */
export function CourseCard({ course, labs }: { course: Course; labs: StudentPracticalSummary[] }) {
  const { todo, done } = splitLabs(labs);
  const next = todo[0];
  return (
    <Link
      href={`/student/courses/${course.id}`}
      className="block rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-slate-300 hover:bg-slate-50/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 sm:p-5"
    >
      <p className="text-xs font-medium text-slate-500">{course.code}</p>
      <p className="mt-0.5 truncate text-sm font-semibold text-slate-900">{course.title}</p>
      <p className="mt-0.5 truncate text-xs text-slate-500">{course.faculty_name ?? "Faculty to be assigned"}</p>
      <div className="mt-4">
        <ScoreBar value={done.length} max={labs.length} tone="indigo" />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {labs.length === 0
          ? "No labs published yet"
          : `${done.length} of ${labs.length} done${next ? ` · next ${relativeDue(next.due_at).label.toLowerCase()}` : ""}`}
      </p>
    </Link>
  );
}

/** One tab per course plus Overview; scrolls horizontally on phones. */
export function CourseTabs({ courses, activeId }: { courses: Course[]; activeId: string | null }) {
  const tabs: { id: string | null; href: string; label: string; title?: string }[] = [
    { id: null, href: "/student", label: "Overview" },
    ...courses.map((c) => ({ id: c.id, href: `/student/courses/${c.id}`, label: c.code, title: c.title })),
  ];
  return (
    <nav aria-label="Courses" className="mb-6 flex gap-6 overflow-x-auto border-b border-slate-200">
      {tabs.map((t) => {
        const active = t.id === activeId;
        return (
          <Link
            key={t.href}
            href={t.href}
            title={t.title}
            aria-current={active ? "page" : undefined}
            className={underlineTabCls(active)}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
