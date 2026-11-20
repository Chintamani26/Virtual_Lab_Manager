"use client";

import Link from "next/link";
import { PageContainer } from "@/components/AppShell";
import { PracticalForm } from "@/components/PracticalForm";
import { PageHeader } from "@/components/ui";

export default function NewPracticalPage() {
  return (
    <PageContainer>
      <div className="mx-auto max-w-4xl">
        <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1.5 text-sm text-slate-500">
          <Link href="/faculty" className="hover:text-slate-900">
            Dashboard
          </Link>
          <span aria-hidden>/</span>
          <span className="text-slate-700">New practical</span>
        </nav>
        <PageHeader title="New practical" />
        <PracticalForm />
      </div>
    </PageContainer>
  );
}
