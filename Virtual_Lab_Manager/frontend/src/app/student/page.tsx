"use client";

import { PageContainer } from "@/components/AppShell";
import { CourseCard, CourseTabs, LabColumns } from "@/components/StudentLabs";
import { Card, EmptyState, ErrorState, PageHeader, PageSkeleton, RoleBadge, StatTile } from "@/components/ui";
import { api, fmtScore } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** Overview across all courses: progress per course, then every lab split into To do | Completed. */
export default function StudentDashboardPage() {
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

  const { user, courses, practicals, stats } = data;

  return (
    <PageContainer>
      <CourseTabs courses={courses} activeId={null} />
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
            <span>My Labs</span>
            <RoleBadge role="student" />
          </span>
        }
        subtitle={[user.roll_number, `${courses.length} ${courses.length === 1 ? "course" : "courses"}`]
          .filter(Boolean)
          .join(" · ")}
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatTile label="Labs completed" value={`${stats.completed}/${stats.assigned}`} hint={`${Math.round((stats.completed / (stats.assigned || 1)) * 100)}% completion rate`} />
        <StatTile label="Average score" value={stats.avg_score === null ? "—" : fmtScore(stats.avg_score, 10)} hint="Out of 10.0 rubric points" />
        <StatTile label="Hints used" value={stats.hints_used} hint="Gemini Socratic tutor guidance" />
      </div>

      {courses.length === 0 ? (
        <Card className="mt-6">
          <EmptyState title="You are not enrolled in any lab courses." />
        </Card>
      ) : (
        <>
          <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-900">Courses</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
            {courses.map((c) => (
              <CourseCard key={c.id} course={c} labs={practicals.filter((p) => p.course_id === c.id)} />
            ))}
          </div>

          <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-900">All labs</h2>
          <LabColumns labs={practicals} showCourse />
        </>
      )}
    </PageContainer>
  );
}
