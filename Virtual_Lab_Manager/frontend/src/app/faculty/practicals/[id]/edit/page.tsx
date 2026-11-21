"use client";

import { useParams } from "next/navigation";
import { PageContainer } from "@/components/AppShell";
import { PracticalForm } from "@/components/PracticalForm";
import { ErrorState, PageSkeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { PracticalHeader } from "@/app/faculty/_components/PracticalHeader";

export default function EditPracticalPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi(() => api.getPractical(id), [id]);

  return (
    <PageContainer>
      {loading && !data ? (
        <PageSkeleton />
      ) : error || !data ? (
        <ErrorState message={error ?? "Practical not found"} onRetry={reload} />
      ) : (
        <>
          <PracticalHeader
            practicalId={id}
            title={data.title}
            status={data.status}
            subtitle={`${data.course_code} · ${data.course_title}`}
            activeTab="edit"
          />
          <div className="max-w-4xl">
            <PracticalForm key={data.id} existing={data} />
          </div>
        </>
      )}
    </PageContainer>
  );
}
