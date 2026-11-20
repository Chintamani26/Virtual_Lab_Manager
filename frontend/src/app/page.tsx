"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
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

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoAccount[] | null>(null);

  useEffect(() => {
    const u = getStoredUser();
    if (getToken() && u) {
      router.replace(homeForRole(u.role));
      return;
    }
    api
      .demoAccounts()
      .then((list) => setDemo(uniqueByRole(list)))
      .catch(() => setDemo([]));
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
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Virtual Lab Manager</h1>
          <p className="mt-1 text-sm text-slate-500">Online practical labs and grading.</p>
        </div>

        <Card className="p-6">
          <h2 className="text-base font-semibold text-slate-900">Sign in</h2>

          <form onSubmit={onSubmit} className="mt-5 space-y-4">
            <Field label="Email">
              <input
                id="email"
                type="email"
                autoComplete="username"
                className={inputCls}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Password">
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className={inputCls}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <InlineError message={error} />
            <Button type="submit" className="w-full" loading={loading === "form"} disabled={loading !== null}>
              Sign in
            </Button>
          </form>

          {demo && demo.length > 0 && (
            <>
              <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
                <div className="h-px flex-1 bg-slate-200" />
                Demo access
                <div className="h-px flex-1 bg-slate-200" />
              </div>
              <div className="grid gap-2">
                {demo.map((d) => {
                  const key = `demo-${d.role}`;
                  return (
                    <Button
                      key={d.role}
                      variant="secondary"
                      className="w-full"
                      loading={loading === key}
                      disabled={loading !== null}
                      onClick={() => doLogin(d.email, d.password, key)}
                    >
                      Login as {ROLE_LABEL[d.role]}
                    </Button>
                  );
                })}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
