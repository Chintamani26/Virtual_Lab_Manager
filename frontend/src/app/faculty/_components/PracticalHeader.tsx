"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { PageHeader, StatusBadge, underlineTabCls } from "@/components/ui";
import type { PracticalStatus } from "@/lib/types";

export type PracticalTab = "submissions" | "monitor" | "edit";

/** Shared breadcrumb, title and underline tab bar across a practical's sub-pages. */
export function PracticalHeader({
  practicalId,
  title,
  status,
  subtitle,
  activeTab,
  actions,
}: {
  practicalId: string;
  title: string;
  status?: PracticalStatus;
  subtitle?: ReactNode;
  activeTab: PracticalTab;
  actions?: ReactNode;
}) {
  const tabs: { key: PracticalTab; href: string; label: string }[] = [
    { key: "submissions", href: `/faculty/practicals/${practicalId}/submissions`, label: "Submissions" },
    { key: "monitor", href: `/faculty/practicals/${practicalId}/monitor`, label: "Live monitor" },
    { key: "edit", href: `/faculty/practicals/${practicalId}/edit`, label: "Settings" },
  ];

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
        <Link href="/faculty" className="hover:text-slate-900">
          Dashboard
        </Link>
        <span aria-hidden>/</span>
        <span className="text-slate-700">{title}</span>
      </nav>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            <span>{title}</span>
            {status && <StatusBadge status={status} />}
          </span>
        }
        subtitle={subtitle}
        actions={actions}
      />

      <nav aria-label="Practical sections" className="mb-6 flex gap-6 overflow-x-auto border-b border-slate-200">
        {tabs.map((t) => {
          const active = t.key === activeTab;
          return (
            <Link key={t.key} href={t.href} aria-current={active ? "page" : undefined} className={underlineTabCls(active)}>
              {t.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
