"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { clearSession, getStoredUser, getToken, homeForRole } from "@/lib/api";
import type { Role, User } from "@/lib/types";
import { AlertsBell } from "./AlertsBell";
import { cx } from "./ui";

const UserContext = createContext<User | null>(null);

export function useUser(): User {
  const u = useContext(UserContext);
  if (!u) throw new Error("useUser must be used inside <RoleGuard>");
  return u;
}

const ROLE_LABEL: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty",
  hod: "HOD",
};

const NAV: Record<Role, { href: string; label: string }[]> = {
  student: [{ href: "/student", label: "My labs" }],
  faculty: [
    { href: "/faculty", label: "Dashboard" },
    { href: "/faculty/practicals/new", label: "New practical" },
    { href: "/faculty/teaching", label: "Teaching material" },
  ],
  hod: [
    { href: "/hod", label: "Department" },
    { href: "/faculty", label: "Faculty view" },
  ],
};

/** Client-side guard: requires a session and one of `roles`; otherwise redirects. */
export function RoleGuard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const token = getToken();
    const u = getStoredUser();
    if (!token || !u) {
      router.replace("/");
      return;
    }
    if (!roles.includes(u.role)) {
      router.replace(homeForRole(u.role));
      return;
    }
    setUser(u);
    // roles is a static literal per layout
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 bg-slate-50 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }
  return <UserContext.Provider value={user}>{children}</UserContext.Provider>;
}

export function TopNav() {
  const user = useUser();
  const pathname = usePathname();
  const items = NAV[user.role];
  // highlight the longest nav href that prefixes the current path
  const activeHref = items
    .filter((x) => pathname === x.href || pathname.startsWith(x.href + "/"))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return (
    <header className="sticky top-0 z-30 h-14 border-b border-slate-800 bg-slate-950">
      <div className="mx-auto flex h-full w-full max-w-7xl items-center gap-4 px-4 sm:gap-8 sm:px-6">
        {/* wordmark is hidden on phones when role nav links exist so links, bell and account fit at 360px */}
        <Link
          href={homeForRole(user.role)}
          className={cx("shrink-0 text-sm font-semibold text-white", items.length > 0 && "hidden sm:inline")}
        >
          Virtual Lab Manager
        </Link>
        {items.length > 0 && (
          <nav className="flex min-w-0 items-center gap-4 text-sm sm:gap-6">
            {items.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                aria-current={activeHref === n.href ? "page" : undefined}
                className={cx(
                  "whitespace-nowrap py-1 transition-colors",
                  activeHref === n.href ? "font-medium text-white" : "text-slate-400 hover:text-white",
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
          {user.role !== "student" && <AlertsBell />}
          <SignedInUser user={user} />
        </div>
      </div>
    </header>
  );
}

/** Signed-in role + Log out. There is deliberately no role switching: a session is one person in one role. */
function SignedInUser({ user }: { user: User }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="hidden text-slate-400 sm:inline" title={user.full_name}>
        {ROLE_LABEL[user.role]}
      </span>
      <button
        type="button"
        onClick={() => {
          clearSession();
          window.location.assign("/");
        }}
        className="rounded-md px-2 py-1 text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
      >
        Log out
      </button>
    </div>
  );
}

/** Standard page container for dashboards. */
export function PageContainer({ children }: { children: ReactNode }) {
  return <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>;
}
