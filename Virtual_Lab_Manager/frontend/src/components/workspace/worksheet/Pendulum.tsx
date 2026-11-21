"use client";

import { useEffect, useRef, useState } from "react";
import { cx } from "@/components/ui";
import { gauss } from "@/lib/worksheet";

const SWING = 0.18; // amplitude in radians (~10°): small-angle regime, so T = 2π√(L/g)
const OSCILLATIONS = 10;

type Timing =
  | { status: "idle" }
  | { status: "running"; elapsed: number; length: number }
  | { status: "done"; reading: number; length: number };

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Virtual simple pendulum. The student sets L, times 10 oscillations with the stopwatch (it stops by itself; the
 * reading carries a small human reaction-time error) and records (L, t₁₀) into the observation table.
 */
export function PendulumApparatus({
  config,
  onRecord,
  disabled,
  full,
}: {
  config: Record<string, number>;
  onRecord: (row: { L: number; t10: number }) => void;
  disabled: boolean;
  /** the table already has max_rows readings */
  full: boolean;
}) {
  const g = config.g ?? 9.81;
  const minL = config.min_length_m ?? 0.2;
  const maxL = config.max_length_m ?? 1.2;
  const [length, setLength] = useState(0.6);
  const [speed, setSpeed] = useState<1 | 5>(5);
  const [timing, setTiming] = useState<Timing>({ status: "idle" });
  const bobRef = useRef<SVGGElement>(null);
  const clock = useRef(0); // simulated seconds since the swing started
  const timingRef = useRef(timing);
  timingRef.current = timing;
  const period = 2 * Math.PI * Math.sqrt(length / g);

  // one animation loop drives both the swing and the stopwatch
  useEffect(() => {
    const still = reducedMotion();
    let raf = 0;
    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000) * speed;
      last = now;
      clock.current += dt;
      const angle = still ? 0 : SWING * Math.cos((2 * Math.PI * clock.current) / period);
      bobRef.current?.setAttribute("transform", `rotate(${(angle * 180) / Math.PI} 140 24)`);
      const t = timingRef.current;
      if (t.status === "running") {
        const elapsed = t.elapsed + dt;
        if (elapsed >= OSCILLATIONS * period) {
          // the stopwatch stops after 10 swings; start + stop reaction error ≈ ±0.05 s
          const reading = Math.round((OSCILLATIONS * period + gauss(0.05)) * 100) / 100;
          setTiming({ status: "done", reading, length: t.length });
        } else {
          setTiming({ ...t, elapsed });
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [period, speed]);

  function start() {
    clock.current = 0; // release from the extreme position as the stopwatch starts
    setTiming({ status: "running", elapsed: 0, length });
  }

  const running = timing.status === "running";
  const shown = timing.status === "running" ? timing.elapsed : timing.status === "done" ? timing.reading : 0;
  const count = timing.status === "running" ? Math.min(OSCILLATIONS, Math.floor(timing.elapsed / period)) : timing.status === "done" ? OSCILLATIONS : 0;
  const canRecord = timing.status === "done" && timing.length === length && !disabled && !full;
  const stringPx = 50 + ((length - minL) / (maxL - minL)) * 170;

  return (
    <div className="grid gap-5 sm:grid-cols-[240px_minmax(0,1fr)]">
      <svg viewBox="0 0 280 290" className="h-auto w-full max-w-[260px] justify-self-center" role="img" aria-label={`Pendulum of length ${length.toFixed(2)} m`}>
        <rect x="40" y="14" width="200" height="10" rx="2" fill="#1c202b" stroke="rgba(255,255,255,0.12)" />
        <line x1="140" y1="24" x2="140" y2="270" stroke="rgba(255,255,255,0.06)" strokeDasharray="4 4" />
        <g ref={bobRef}>
          <line x1="140" y1="24" x2="140" y2={24 + stringPx} stroke="#9aa3b2" strokeWidth="1.5" />
          <circle cx="140" cy={24 + stringPx + 12} r="12" fill="#818cf8" stroke="#0f1117" strokeWidth="2" />
        </g>
        <circle cx="140" cy="24" r="3" fill="#e6e8ee" />
        {/* metre rule beside the pendulum */}
        <line x1="252" y1="24" x2="252" y2={24 + stringPx + 12} stroke="#fbbf24" strokeWidth="1.5" />
        <line x1="246" y1="24" x2="258" y2="24" stroke="#fbbf24" strokeWidth="1.5" />
        <line x1="246" y1={24 + stringPx + 12} x2="258" y2={24 + stringPx + 12} stroke="#fbbf24" strokeWidth="1.5" />
        <text x="246" y={30 + (stringPx + 12) / 2} fill="#fbbf24" fontSize="12" textAnchor="end" fontFamily="var(--font-jetbrains)">
          {length.toFixed(2)} m
        </text>
      </svg>

      <div className="min-w-0 space-y-4">
        <div>
          <div className="flex items-baseline justify-between">
            <label htmlFor="pendulum-length" className="text-xs text-fg-muted">
              Length L
            </label>
            <span className="font-mono text-sm text-fg">{length.toFixed(2)} m</span>
          </div>
          <input
            id="pendulum-length"
            type="range"
            min={minL}
            max={maxL}
            step={0.05}
            value={length}
            disabled={running || disabled}
            onChange={(e) => {
              setLength(Number(e.target.value));
              setTiming({ status: "idle" });
            }}
            className="mt-2 w-full accent-indigo-500"
          />
          <div className="mt-0.5 flex justify-between font-mono text-[10px] text-fg-faint">
            <span>{minL.toFixed(2)} m</span>
            <span>{maxL.toFixed(2)} m</span>
          </div>
        </div>

        <div className="rounded-lg border border-line bg-canvas px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-fg-faint">Stopwatch</span>
            <span className="text-xs text-fg-faint" data-testid="oscillation-count">
              Oscillations {count} / {OSCILLATIONS}
            </span>
          </div>
          <p className={cx("mt-1 font-mono text-3xl tabular-nums", timing.status === "done" ? "text-emerald-300" : "text-fg")} data-testid="stopwatch">
            {shown.toFixed(2)} <span className="text-base text-fg-faint">s</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={start} disabled={running || disabled} className="btn btn-secondary">
            {running ? "Timing…" : timing.status === "done" ? "Time again" : `Time ${OSCILLATIONS} oscillations`}
          </button>
          <button
            onClick={() => {
              if (timing.status !== "done") return;
              onRecord({ L: Number(length.toFixed(2)), t10: timing.reading });
              setTiming({ status: "idle" });
            }}
            disabled={!canRecord}
            className="btn btn-primary"
            data-testid="record-reading"
          >
            Record reading
          </button>
          <div className="ml-auto flex overflow-hidden rounded-ctl ring-1 ring-inset ring-line-strong" role="group" aria-label="Simulation speed">
            {([1, 5] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                aria-pressed={speed === s}
                className={cx("h-8 px-2.5 font-mono text-xs", speed === s ? "bg-surface-3 text-fg" : "text-fg-faint hover:text-fg-muted")}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-fg-faint">
          {full
            ? "The table is full. Remove a reading to take another."
            : "Set a length, time 10 oscillations, then record the reading. Use 5× to speed up the simulation."}
        </p>
      </div>
    </div>
  );
}
