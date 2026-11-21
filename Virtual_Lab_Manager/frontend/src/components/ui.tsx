"use client";

import { Children, type ReactNode, type ButtonHTMLAttributes } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/*
 * Light-page primitives follow the house style in docs/DESIGN_SYSTEM.md ("Minimal UI rules"):
 * white cards with a slate-200 border, one indigo accent, status colours only for status, no decorative icons.
 * `icon` / `tone` props are still accepted everywhere for backward compatibility; decorative slots ignore them.
 */

// ---------- layout primitives ----------
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("rounded-xl border border-slate-200/90 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.02),0_4px_12px_rgba(0,0,0,0.03)] transition-all", className)}>{children}</div>;
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  /** @deprecated decorative; no longer rendered */
  icon?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Plain KPI tile: label, number, optional one-line meta. `icon` and `tone` are accepted but not rendered. */
export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  /** @deprecated decorative; no longer rendered */
  icon?: ReactNode;
  /** @deprecated decorative; no longer rendered */
  tone?: "indigo" | "emerald" | "amber" | "rose" | "sky" | "violet";
}) {
  return (
    <Card className="p-4 sm:p-5 hover:border-slate-300 hover:shadow-[0_4px_20px_-4px_rgba(99,102,241,0.06)] transition-all">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1.5 text-2xl font-bold tracking-tight tabular-nums text-slate-900 sm:text-3xl">{value}</p>
      {hint && <p className="mt-1.5 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}

// ---------- buttons ----------
type Variant = "primary" | "secondary" | "ghost" | "danger" | "success" | "dark" | "ai";
type Size = "sm" | "md";

// One accent: "success" renders as primary and "dark" as secondary (kept as names for existing call sites).
const BTN_PRIMARY = "bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm shadow-indigo-600/20 active:scale-[0.98] transition-all";
const BTN_SECONDARY = "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-900 hover:border-slate-300 shadow-sm active:scale-[0.98] transition-all";
const BTN_AI = "bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-500 hover:to-violet-500 shadow-sm shadow-indigo-500/25 active:scale-[0.98] transition-all";
const BTN_VARIANTS: Record<Variant, string> = {
  primary: BTN_PRIMARY,
  secondary: BTN_SECONDARY,
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all",
  danger: "bg-rose-600 text-white hover:bg-rose-500 shadow-sm shadow-rose-600/20 active:scale-[0.98] transition-all",
  success: BTN_PRIMARY,
  dark: BTN_SECONDARY,
  ai: BTN_AI,
};
const BTN_SIZES: Record<Size, string> = { sm: "h-8 px-3 text-[13px] gap-1.5", md: "h-9 px-4 text-sm gap-2" };

export function buttonClasses(variant: Variant = "primary", size: Size = "md", className?: string) {
  return cx(
    "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600",
    "disabled:cursor-not-allowed disabled:opacity-50",
    BTN_VARIANTS[variant],
    BTN_SIZES[size],
    className,
  );
}

/** Buttons are text-only: `icon` renders only for icon-only buttons (no children; give them an aria-label). */
function hasContent(children: ReactNode) {
  return Children.toArray(children).length > 0;
}

export function Button({
  variant = "primary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}) {
  const iconOnly = !hasContent(children);
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={buttonClasses(variant, size, cx(iconOnly && (size === "sm" ? "w-8 px-0" : "w-9 px-0"), className))}
    >
      {loading ? <Loader2 className={size === "sm" ? "h-3.5 w-3.5 animate-spin" : "h-4 w-4 animate-spin"} /> : iconOnly && icon}
      {children}
    </button>
  );
}

/** A Next.js link styled as a button (avoids nesting <button> inside <a>). */
export function LinkButton({
  href,
  variant = "primary",
  size = "md",
  icon,
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  /** only rendered for icon-only links */
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={buttonClasses(variant, size, className)}>
      {!hasContent(children) && icon}
      {children}
    </Link>
  );
}

// ---------- badges ----------
type BadgeTone = "slate" | "indigo" | "emerald" | "amber" | "rose" | "sky" | "violet";

const BADGE_TONES: Record<BadgeTone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200/80",
  indigo: "bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-600/20",
  emerald: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
  amber: "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/20",
  rose: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-600/20",
  sky: "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-600/20",
  violet: "bg-violet-50 text-violet-700 ring-1 ring-inset ring-violet-600/20",
};

/** Small status label. Use only for real status (Graded, Overdue, Locked, risk level), never as decoration. */
export function Badge({
  children,
  tone = "slate",
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium tracking-tight",
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "published" || status === "reviewed" || status === "compliant"
      ? "emerald"
      : status === "graded"
        ? "indigo"
        : status === "at_risk"
          ? "amber"
          : status === "non_compliant"
            ? "rose"
            : "slate";
  const label = status.replace(/_/g, " ");
  return (
    <Badge tone={tone}>
      <span
        className={cx(
          "h-1.5 w-1.5 shrink-0 rounded-full",
          tone === "emerald"
            ? "bg-emerald-500"
            : tone === "indigo"
              ? "bg-indigo-500"
              : tone === "amber"
                ? "bg-amber-500"
                : tone === "rose"
                  ? "bg-rose-500"
                  : "bg-slate-400",
        )}
      />
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </Badge>
  );
}

export function RoleBadge({
  role,
  className,
}: {
  role: "student" | "faculty" | "hod";
  className?: string;
}) {
  const cfg = {
    student: {
      label: "Student",
      tone: "bg-emerald-500/10 text-emerald-700 border-emerald-500/25 ring-emerald-500/10",
      dot: "bg-emerald-500",
    },
    faculty: {
      label: "Faculty",
      tone: "bg-indigo-500/10 text-indigo-700 border-indigo-500/25 ring-indigo-500/10",
      dot: "bg-indigo-500",
    },
    hod: {
      label: "HOD",
      tone: "bg-purple-500/10 text-purple-700 border-purple-500/25 ring-purple-500/10",
      dot: "bg-purple-500",
    },
  }[role];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ring-1",
        cfg.tone,
        className,
      )}
    >
      <span className={cx("h-1.5 w-1.5 rounded-full animate-pulse", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

// ---------- states ----------
export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-slate-200/60", className)} />;
}

export function PageSkeleton({ tiles = 4 }: { tiles?: 3 | 4 } = {}) {
  return (
    <div className="space-y-6">
      <Skeleton className="h-7 w-48" />
      <div className={cx("grid gap-4", tiles === 3 ? "grid-cols-3" : "grid-cols-2 lg:grid-cols-4")}>
        {Array.from({ length: tiles }).map((_, i) => (
          <Skeleton key={i} className="h-[88px]" />
        ))}
      </div>
      <Skeleton className="h-64" />
      <Skeleton className="h-48" />
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card className="p-6 text-center">
      <p className="text-sm font-semibold text-slate-900">Something went wrong</p>
      <p className="mt-1 text-sm text-slate-500">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      )}
    </Card>
  );
}

/** One short muted line (plus optional detail/action). No icon, no illustration. */
export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="px-5 py-6">
      <p className="text-sm text-slate-500">{title}</p>
      {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
      {message}
    </div>
  );
}

// ---------- form fields ----------
export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

// NOTE: PracticalForm derives an error variant by string-replacing "border-slate-300",
// "focus:border-indigo-500" and "focus:ring-indigo-500/20"; keep those tokens.
export const inputCls =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-[7px] text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:text-slate-500";

export const compactSelectCls =
  "h-8 rounded-md border border-slate-300 bg-white px-2.5 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-50 disabled:text-slate-500";

// ---------- navigation & filters ----------
export function underlineTabCls(active: boolean) {
  return cx(
    "-mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 pb-2.5 text-sm transition-colors",
    active ? "border-indigo-600 font-medium text-slate-900" : "border-transparent text-slate-500 hover:text-slate-900",
  );
}

export function UnderlineTabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
  className,
}: {
  tabs: { key: T; label: string; count?: number }[];
  active: T;
  onChange: (key: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <nav aria-label={label} className={cx("flex gap-6 overflow-x-auto border-b border-slate-200", className)}>
      {tabs.map((t) => {
        const isActive = active === t.key;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-current={isActive ? "page" : undefined}
            className={underlineTabCls(isActive)}
          >
            <span>{t.label}</span>
            {t.count !== undefined && <span className="text-xs tabular-nums text-slate-400">{t.count}</span>}
          </button>
        );
      })}
    </nav>
  );
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div role="group" aria-label={ariaLabel} className="inline-flex rounded-md border border-slate-200 bg-white p-0.5 text-xs">
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(opt.value)}
            className={cx(
              "whitespace-nowrap rounded px-2.5 py-1 transition-colors",
              active ? "bg-slate-100 font-medium text-slate-900" : "text-slate-500 hover:text-slate-800",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

export function ScoreBar({ value, max, tone }: { value: number; max: number; tone?: "auto" | "indigo" }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const color =
    tone === "indigo" ? "bg-indigo-600" : pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div className={cx("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

// =====================================================================================
// Dark workspace primitives (tokens + patterns: src/app/globals.css, docs/DESIGN_SYSTEM.md)
// =====================================================================================

/** Shimmer placeholder for dark surfaces — size it exactly like the content it replaces. */
export function DarkSkeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("skeleton-dark", className)} />;
}

/** "⌘" on Apple platforms, "Ctrl" elsewhere (client-only; workspace renders after data loads). */
export function modKey(): string {
  if (typeof navigator === "undefined") return "⌘";
  return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘" : "Ctrl";
}
