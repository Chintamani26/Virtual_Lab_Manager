"use client";

import type { ReactNode } from "react";
import { RoleGuard, TopNav } from "@/components/AppShell";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <RoleGuard roles={["hod"]}>
      <div className="flex min-h-screen flex-col">
        <TopNav />
        {children}
      </div>
    </RoleGuard>
  );
}
