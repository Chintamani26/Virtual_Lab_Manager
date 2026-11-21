"use client";

import { useParams } from "next/navigation";
import { PageContainer } from "@/components/AppShell";
import { CourseTabs, LabColumns, splitLabs } from "@/components/StudentLabs";
import { Card, EmptyState, ErrorState, LinkButton, PageHeader, PageSkeleton, StatTile } from "@/components/ui";
import { api, fmtScore, relativeDue } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** One page per course: course details, then its labs split into To do | Completed. */
export default function StudentCoursePage() {
  const { id } = useParams<{ id: string }>();
  // the dashboard payload already holds every course and lab for this student, so reuse it
  const { data, error, loading, reload } = useApi(() => api.studentDashboard());

  if (loading && !data)
    return (
      <PageContainer>
        <PageSkeleton tiles={3} />
      </PageContainer>
    );
  if (error || !data)
    return (
      <PageContainer>
        <ErrorState message={error ?? "No data"} onRetry={reload} />
      </PageContainer>
    );

  const course = data.courses.find((c) => c.id === id);
  if (!course)
    return (
      <PageContainer>
        <CourseTabs courses={data.courses} activeId={id} />
        <Card>
          <EmptyState
            title="This course is not in your enrolled courses."
            action={
              <LinkButton href="/student" variant="secondary" size="sm">
                Back to overview
              </LinkButton>
            }
          />
        </Card>
      </PageContainer>
    );

  const labs = data.practicals.filter((p) => p.course_id === course.id);
  const { todo, done } = splitLabs(labs);
  const scores = done.filter((p) => p.best_score !== null).map((p) => (p.best_score! / p.max_score) * 10);
  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const next = todo[0];

  return (
    <PageContainer>
      <CourseTabs courses={data.courses} activeId={course.id} />
      <PageHeader
        title={course.title}
        subtitle={`${course.code} · Semester ${course.semester} · ${course.faculty_name ?? "Faculty to be assigned"}`}
      />

      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <StatTile label="Labs completed" value={`${done.length}/${labs.length}`} />
        <StatTile label="Average score" value={avg === null ? "—" : fmtScore(Math.round(avg * 10) / 10, 10)} />
        <StatTile label="Next deadline" value={next ? relativeDue(next.due_at).label : "—"} hint={next?.title} />
      </div>

      <div className="mt-8">
        {labs.length === 0 ? (
          <Card>
            <EmptyState title="No labs published in this course yet." />
          </Card>
        ) : (
          <LabColumns labs={labs} showCourse={false} />
        )}
      </div>
    </PageContainer>
  );
}
