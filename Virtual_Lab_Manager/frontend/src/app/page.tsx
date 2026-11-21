"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { api, getStoredUser, getToken, homeForRole, setSession } from "@/lib/api";
import type { DemoAccount, Role } from "@/lib/types";
import { Button, Card, Field, InlineError, inputCls } from "@/components/ui";

const ROLE_LABEL: Record<Role, string> = { student: "Student", faculty: "Faculty", hod: "HOD" };
const ROLE_ORDER: Role[] = ["student", "faculty", "hod"];

/** Keep at most one demo account per role so demo login only exposes clean role options. */
function uniqueByRole(list: DemoAccount[]): DemoAccount[] {
  const seen = new Set<Role>();
  return [...list]
    .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role))
    .filter((item) => {
      if (seen.has(item.role)) return false;
      seen.add(item.role);
      return true;
    });
}

const DEFAULT_DEMOS: DemoAccount[] = [
  { role: "student", full_name: "Aarav Sharma", email: "aarav.sharma@demo.edu", password: "demo1234" },
  { role: "faculty", full_name: "Meera Kulkarni", email: "meera.kulkarni@demo.edu", password: "demo1234" },
  { role: "hod", full_name: "Rajesh Deshpande", email: "rajesh.deshpande@demo.edu", password: "demo1234" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoAccount[]>(DEFAULT_DEMOS);

  useEffect(() => {
    const u = getStoredUser();
    if (getToken() && u) {
      router.replace(homeForRole(u.role));
      return;
    }
    api
      .demoAccounts()
      .then((list) => {
        if (list && list.length > 0) {
          setDemo(uniqueByRole(list));
        }
      })
      .catch(() => {
        // Keep DEFAULT_DEMOS fallback
      });
  }, [router]);

  async function doLogin(e: string, p: string, key: string) {
    setError(null);
    setLoading(key);
    try {
      const res = await api.login(e, p);
      setSession(res.access_token, res.user);
      router.replace(homeForRole(res.user.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
      setLoading(null);
    }
  }

  function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!email || !password) {
      setError("Enter your email and password.");
      return;
    }
    void doLogin(email, password, "form");
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-12 relative overflow-hidden">
      {/* Background glowing gradients */}
      <div className="pointer-events-none absolute -top-40 -left-40 h-96 w-96 rounded-full bg-indigo-500/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-purple-500/15 blur-3xl" />

      <div className="w-full max-w-md relative z-10">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-purple-500/30 bg-purple-500/10 px-3 py-1 text-xs font-medium text-purple-300 mb-3">
            <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-pulse" />
            Gemini 3.5 Socratic Lab Platform
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Virtual Lab Manager</h1>
          <p className="mt-2 text-sm text-slate-400">
            Interactive engineering labs, Socratic AI tutor & automated rubric evaluation.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/90 p-6 sm:p-8 shadow-2xl backdrop-blur-xl">
          <div className="mb-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">One-Click Judging Access</h2>
            <p className="mt-1 text-xs text-slate-500">Select any role to experience the platform end-to-end:</p>
          </div>

          {demo && demo.length > 0 && (
            <div className="grid gap-2.5 mb-6">
              {demo.map((d) => {
                const key = `demo-${d.role}`;
                const meta = {
                  student: { icon: "🎓", label: "Student", desc: "Aarav Sharma · Lab 4 BST, hints & submit" },
                  faculty: { icon: "🧑‍🏫", label: "Faculty", desc: "Meera Kulkarni · Auto-grading & submissions" },
                  hod: { icon: "🏛️", label: "HOD", desc: "Rajesh Deshpande · Department intelligence" },
                }[d.role];
                return (
                  <button
                    key={d.role}
                    type="button"
                    disabled={loading !== null}
                    onClick={() => doLogin(d.email, d.password, key)}
                    className="flex w-full items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 text-left transition hover:border-indigo-500/50 hover:bg-slate-800/80 disabled:opacity-50 group"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xl">{meta.icon}</span>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-slate-200 group-hover:text-white">
                            {meta.label}
                          </span>
                          <span className="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-medium text-indigo-400 border border-indigo-500/20">
                            Demo
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">{meta.desc}</p>
                      </div>
                    </div>
                    {loading === key ? (
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
                    ) : (
                      <span className="text-xs font-semibold text-slate-400 group-hover:text-indigo-400 transition-colors">
                        Enter →
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
            <div className="h-px flex-1 bg-slate-800" />
            or sign in with credentials
            <div className="h-px flex-1 bg-slate-800" />
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Email address</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="name@demo.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2 text-sm text-white placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <InlineError message={error} />
            <Button
              type="submit"
              variant="primary"
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2 rounded-lg"
              loading={loading === "form"}
              disabled={loading !== null}
            >
              Sign in with password
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
