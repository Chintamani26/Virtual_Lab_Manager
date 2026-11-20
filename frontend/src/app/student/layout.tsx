"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { RoleGuard, TopNav } from "@/components/AppShell";

export default function Layout({ children }: { children: ReactNode }) {
  // The lab workspace is an immersive, full-height IDE with its own header (LabHeader).
  const immersive = usePathname().startsWith("/student/labs/");
  return (
    <RoleGuard roles={["student"]}>
      <div className="flex min-h-screen flex-col">
        {!immersive && <TopNav />}
        {children}
      </div>
    </RoleGuard>
  );
}
