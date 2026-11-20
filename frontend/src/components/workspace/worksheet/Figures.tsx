"use client";

import { useId } from "react";
import { fitLine, fmtTick, ticks } from "@/lib/worksheet";

// Dark workspace palette (docs/DESIGN_SYSTEM.md): axes/grids are hairlines, data is brand, constructions are amber.
const AXIS = "rgba(255,255,255,0.22)";
const GRID = "rgba(255,255,255,0.06)";
const TEXT = "#9aa3b2";
const FAINT = "#6b7280";
const BRAND = "#818cf8";
const AMBER = "#fbbf24";

/** Scatter of the observation table with its least-squares line; axes start at 0 (both experiments pass through it). */
export function ScatterGraph({
  points,
  xLabel,
  yLabel,
}: {
  points: [number, number][];
  xLabel: string;
  yLabel: string;
}) {
  const W = 520;
  const H = 300;
  const m = { l: 56, r: 16, t: 14, b: 44 };
  const xs = ticks(Math.max(...points.map((p) => p[0]), 0) * 1.1 || 1);
  const ys = ticks(Math.max(...points.map((p) => p[1]), 0) * 1.1 || 1);
  const xMax = xs[xs.length - 1];
  const yMax = ys[ys.length - 1];
  const X = (v: number) => m.l + (v / xMax) * (W - m.l - m.r);
  const Y = (v: number) => H - m.b - (v / yMax) * (H - m.t - m.b);
  const fit = fitLine(points);
  const clip = useId();

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`Graph of ${yLabel} against ${xLabel}`}>
      {xs.map((t) => (
        <g key={`x${t}`}>
          <line x1={X(t)} x2={X(t)} y1={m.t} y2={H - m.b} stroke={GRID} />
          <text x={X(t)} y={H - m.b + 16} fill={TEXT} fontSize="11" textAnchor="middle" fontFamily="var(--font-jetbrains)">
            {fmtTick(t)}
          </text>
        </g>
      ))}
      {ys.map((t) => (
        <g key={`y${t}`}>
          <line x1={m.l} x2={W - m.r} y1={Y(t)} y2={Y(t)} stroke={GRID} />
          <text x={m.l - 8} y={Y(t) + 4} fill={TEXT} fontSize="11" textAnchor="end" fontFamily="var(--font-jetbrains)">
            {fmtTick(t)}
          </text>
        </g>
      ))}
      <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} stroke={AXIS} />
      <line x1={m.l} x2={m.l} y1={m.t} y2={H - m.b} stroke={AXIS} />
      <text x={(m.l + W - m.r) / 2} y={H - 8} fill={TEXT} fontSize="12" textAnchor="middle">
        {xLabel}
      </text>
      <text x={14} y={(m.t + H - m.b) / 2} fill={TEXT} fontSize="12" textAnchor="middle" transform={`rotate(-90 14 ${(m.t + H - m.b) / 2})`}>
        {yLabel}
      </text>
      <clipPath id={clip}>
        <rect x={m.l} y={m.t} width={W - m.l - m.r} height={H - m.t - m.b} />
      </clipPath>
      {fit && (
        <line
          x1={X(0)}
          y1={Y(fit.c)}
          x2={X(xMax)}
          y2={Y(fit.m * xMax + fit.c)}
          stroke={BRAND}
          strokeWidth="1.5"
          opacity="0.7"
          clipPath={`url(#${clip})`}
        />
      )}
      {points.map(([x, y], i) => (
        <circle key={i} cx={X(x)} cy={Y(y)} r="4" fill={BRAND} stroke="#0f1117" strokeWidth="1.5" />
      ))}
      {points.length === 0 && (
        <text x={(m.l + W - m.r) / 2} y={(m.t + H - m.b) / 2} fill={FAINT} fontSize="12" textAnchor="middle">
          Points appear as you fill in the table
        </text>
      )}
    </svg>
  );
}

/** f(x) = x³ − 2x − 5 with the tangent construction drawn from the student's own x₁ and x₂. */
export function NewtonFigure({ x1, x2 }: { x1: number | null; x2: number | null }) {
  const f = (x: number) => x ** 3 - 2 * x - 5;
  const W = 300;
  const H = 230;
  const m = { l: 34, r: 12, t: 12, b: 26 };
  const [xa, xb, ya, yb] = [1.8, 2.3, -3, 3];
  const X = (v: number) => m.l + ((v - xa) / (xb - xa)) * (W - m.l - m.r);
  const Y = (v: number) => H - m.b - ((v - ya) / (yb - ya)) * (H - m.t - m.b);
  const inRange = (v: number | null): v is number => v !== null && v >= xa && v <= xb;
  const curve = Array.from({ length: 61 }, (_, i) => xa + ((xb - xa) * i) / 60)
    .map((x, i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(f(x)).toFixed(1)}`)
    .join(" ");
  const x0 = 2;
  const pts: { x: number; label: string }[] = [{ x: x0, label: "x₀" }];
  if (inRange(x1)) pts.push({ x: x1, label: "x₁" });
  if (inRange(x1) && inRange(x2)) pts.push({ x: x2, label: "x₂" });

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Graph of f(x) with Newton–Raphson tangents">
        {[1.8, 1.9, 2, 2.1, 2.2, 2.3].map((t) => (
          <g key={t}>
            <line x1={X(t)} x2={X(t)} y1={m.t} y2={H - m.b} stroke={GRID} />
            <text x={X(t)} y={H - 8} fill={TEXT} fontSize="10" textAnchor="middle" fontFamily="var(--font-jetbrains)">
              {t.toFixed(1)}
            </text>
          </g>
        ))}
        <line x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} stroke={AXIS} />
        <text x={m.l - 6} y={Y(0) + 3} fill={TEXT} fontSize="10" textAnchor="end">0</text>
        <path d={curve} fill="none" stroke={BRAND} strokeWidth="2" />
        {pts.slice(0, -1).map((p, i) => {
          const next = pts[i + 1];
          return (
            <g key={p.label}>
              {/* the student's next estimate: if it's right, this segment lies along the tangent */}
              <line x1={X(p.x)} y1={Y(f(p.x))} x2={X(next.x)} y2={Y(0)} stroke={AMBER} strokeWidth="1.5" />
              <line x1={X(next.x)} y1={Y(0)} x2={X(next.x)} y2={Y(f(next.x))} stroke={AMBER} strokeDasharray="3 3" opacity="0.6" />
            </g>
          );
        })}
        {pts.map((p, i) => (
          <g key={p.label}>
            <circle cx={X(p.x)} cy={Y(f(p.x))} r="3.5" fill={i === 0 ? BRAND : AMBER} />
            <text x={X(p.x) + (i === 0 ? -8 : 6)} y={Y(f(p.x)) + (i === 0 ? 14 : -6)} fill={TEXT} fontSize="11" textAnchor={i === 0 ? "end" : "start"}>
              {p.label}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-[11px] leading-4 text-fg-faint">
        The tangent at each point meets the x-axis at the next estimate. Your x₁ and x₂ draw the amber lines.
      </figcaption>
    </figure>
  );
}

/** f(x) = 1 / (1 + x²) on [0, 1] with the four Simpson strips and the 1-4-2-4-1 weights. */
export function SimpsonFigure() {
  const f = (x: number) => 1 / (1 + x * x);
  const W = 300;
  const H = 230;
  const m = { l: 30, r: 12, t: 22, b: 44 };
  const X = (v: number) => m.l + v * (W - m.l - m.r);
  const Y = (v: number) => H - m.b - (v / 1.1) * (H - m.t - m.b);
  const xs = Array.from({ length: 41 }, (_, i) => i / 40);
  const curve = xs.map((x, i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(f(x)).toFixed(1)}`).join(" ");
  const area = `${curve} L${X(1)},${Y(0)} L${X(0)},${Y(0)} Z`;
  const nodes = [0, 0.25, 0.5, 0.75, 1];
  const weights = [1, 4, 2, 4, 1];

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Area under 1/(1+x²) split into four strips">
        <path d={area} fill={BRAND} opacity="0.12" />
        {nodes.map((x) => (
          <line key={x} x1={X(x)} x2={X(x)} y1={Y(0)} y2={Y(f(x))} stroke={AXIS} strokeDasharray="3 3" />
        ))}
        <path d={curve} fill="none" stroke={BRAND} strokeWidth="2" />
        <line x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} stroke={AXIS} />
        {nodes.map((x, i) => (
          <g key={x}>
            <circle cx={X(x)} cy={Y(f(x))} r="3.5" fill={AMBER} />
            <text x={X(x)} y={Y(f(x)) - 8} fill={TEXT} fontSize="11" textAnchor="middle">
              y{"₀₁₂₃₄"[i]}
            </text>
            <text x={X(x)} y={Y(0) + 14} fill={TEXT} fontSize="10" textAnchor="middle" fontFamily="var(--font-jetbrains)">
              {x}
            </text>
            <text x={X(x)} y={Y(0) + 30} fill={AMBER} fontSize="10" textAnchor="middle" fontFamily="var(--font-jetbrains)">
              ×{weights[i]}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-[11px] leading-4 text-fg-faint">
        Simpson&apos;s weights are 1, 4, 2, 4, 1. The shaded area is the integral you are estimating.
      </figcaption>
    </figure>
  );
}
