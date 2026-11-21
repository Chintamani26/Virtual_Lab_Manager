"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { api, clearSession, getStoredUser, getToken, homeForRole, setSession } from "@/lib/api";
import type { Role, User } from "@/lib/types";
import { AlertsBell } from "./AlertsBell";
import { RoleBadge, cx } from "./ui";

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

const DEMO_PERSONAS: { role: Role; name: string; email: string; icon: string }[] = [
  { role: "student", name: "Aarav Sharma", email: "aarav.sharma@demo.edu", icon: "🎓" },
  { role: "faculty", name: "Meera Kulkarni", email: "meera.kulkarni@demo.edu", icon: "🧑‍🏫" },
  { role: "hod", name: "Rajesh Deshpande", email: "rajesh.deshpande@demo.edu", icon: "🏛️" },
];

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
        <Loader2 className="h-4 w-4 animate-spin text-indigo-600" /> Loading…
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
    <header className="sticky top-0 z-30 h-14 border-b border-slate-800/80 bg-slate-950/95 backdrop-blur-md">
      <div className="mx-auto flex h-full w-full max-w-7xl items-center gap-4 px-4 sm:gap-8 sm:px-6">
        <div className="flex items-center gap-2.5 shrink-0">
          <Link
            href={homeForRole(user.role)}
            className="flex items-center gap-2 text-sm font-semibold text-white tracking-tight hover:opacity-90 transition-opacity"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 shadow-sm shadow-indigo-500/30 text-white font-bold text-xs">
              V
            </span>
            <span className="hidden sm:inline">Virtual Lab Manager</span>
          </Link>
          <span className="hidden md:inline-flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] font-medium text-purple-300">
            <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-pulse" />
            Gemini 3.5
          </span>
        </div>

        {items.length > 0 && (
          <nav className="flex min-w-0 items-center gap-3 sm:gap-6 text-sm">
            {items.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                aria-current={activeHref === n.href ? "page" : undefined}
                className={cx(
                  "relative py-1 text-xs sm:text-sm transition-colors whitespace-nowrap",
                  activeHref === n.href ? "font-semibold text-white" : "text-slate-400 hover:text-white",
                )}
              >
                {n.label}
                {activeHref === n.href && (
                  <span className="absolute -bottom-[15px] inset-x-0 h-0.5 bg-indigo-500 rounded-full" />
                )}
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

/** Signed-in role badge + Quick Persona Switcher for live judging demos + Sign out */
function SignedInUser({ user }: { user: User }) {
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);

  async function switchPersona(email: string) {
    setSwitching(email);
    try {
      const res = await api.login(email, "demo1234");
      setSession(res.access_token, res.user);
      window.location.assign(homeForRole(res.user.role));
    } catch {
      setSwitching(null);
    }
  }

  return (
    <div className="relative flex items-center gap-2 sm:gap-3 text-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Click to switch persona (judging mode)"
        className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/90 px-2.5 py-1 text-left text-xs transition hover:border-slate-700 hover:bg-slate-800"
      >
        <RoleBadge role={user.role} />
        <span className="hidden sm:inline font-medium text-slate-200 truncate max-w-[110px]">
          {user.full_name}
        </span>
        <span className="text-[10px] text-slate-400">▾</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 z-50 w-64 rounded-xl border border-slate-800 bg-slate-950 p-2 shadow-2xl text-xs">
            <p className="px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Demo Personas (1-Click Switch)
            </p>
            <div className="space-y-1 mt-1">
              {DEMO_PERSONAS.map((p) => {
                const isCurrent = user.email === p.email;
                return (
                  <button
                    key={p.email}
                    type="button"
                    disabled={isCurrent || switching !== null}
                    onClick={() => void switchPersona(p.email)}
                    className={cx(
                      "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition-colors",
                      isCurrent
                        ? "bg-indigo-600/20 text-indigo-300 font-semibold cursor-default"
                        : "text-slate-300 hover:bg-slate-900 hover:text-white disabled:opacity-50",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <span>{p.icon}</span>
                      <span>
                        <span className="block font-medium">{p.name}</span>
                        <span className="block text-[10px] text-slate-400">{ROLE_LABEL[p.role]}</span>
                      </span>
                    </span>
                    {switching === p.email ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
                    ) : isCurrent ? (
                      <span className="text-[10px] uppercase font-bold text-indigo-400">Active</span>
                    ) : (
                      <span className="text-[10px] text-slate-400 group-hover:text-white">Switch →</span>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="mt-2 border-t border-slate-800 pt-2 px-1">
              <button
                type="button"
                onClick={() => {
                  clearSession();
                  window.location.assign("/");
                }}
                className="w-full rounded-md px-2 py-1.5 text-center text-xs text-rose-400 hover:bg-rose-500/10 transition-colors"
              >
                Log out
              </button>
            </div>
          </div>
        </>
      )}

      <button
        type="button"
        onClick={() => {
          clearSession();
          window.location.assign("/");
        }}
        className="hidden sm:inline-block rounded-md px-2 py-1 text-xs text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
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
