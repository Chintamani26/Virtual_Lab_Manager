"use client";

import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SegmentedControl, cx } from "./ui";

// One neutral palette: indigo-600 for the plotted series, slate for grid and axes.
const PRIMARY = "#4f46e5"; // indigo-600
const GRID = "#e2e8f0"; // slate-200
const AXIS_TEXT = "#64748b"; // slate-500
const AXIS_TICK = { fontSize: 11, fill: AXIS_TEXT };

type ActivityPoint = { date: string; executions: number; submissions: number; hints: number };
type MetricKey = keyof Omit<ActivityPoint, "date">;

const METRICS: { key: MetricKey; title: string; unit: string }[] = [
  { key: "executions", title: "Code runs", unit: "runs" },
  { key: "submissions", title: "Submissions", unit: "submissions" },
  { key: "hints", title: "Hints", unit: "hints" },
];

function shortDate(d: string) {
  const dt = new Date(`${d}T00:00:00`);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function ChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ value?: unknown }>;
  label?: string | number;
  unit: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0];
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-sm">
      <p className="text-slate-500">{typeof label === "string" && /^\d{4}-/.test(label) ? shortDate(label) : label}</p>
      <p className="mt-0.5 text-slate-700">
        <span className="font-semibold tabular-nums text-slate-900">{String(p.value ?? "")}</span> {unit}
      </p>
    </div>
  );
}

/** Chart / table switch for the activity card header. */
export function ViewToggle({ asTable, onChange }: { asTable: boolean; onChange: (asTable: boolean) => void }) {
  return (
    <SegmentedControl
      ariaLabel="Activity view"
      value={asTable ? "table" : "chart"}
      onChange={(v) => onChange(v === "table")}
      options={[
        { value: "chart", label: "Chart" },
        { value: "table", label: "Table" },
      ]}
    />
  );
}

/** Single focused area chart with a metric switcher (or full 3-column table). */
export function ActivityCharts({ data, asTable = false }: { data: ActivityPoint[]; asTable?: boolean }) {
  const [metric, setMetric] = useState<MetricKey>("executions");

  if (asTable) {
    return (
      <div className="max-h-60 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-white text-xs text-slate-500">
            <tr className="border-b border-slate-200">
              <th className="py-2 pr-3 font-medium">Date</th>
              {METRICS.map((m) => (
                <th key={m.key} className="px-3 py-2 text-right font-medium">
                  {m.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((d) => (
              <tr key={d.date} className="hover:bg-slate-50/60">
                <td className="py-2 pr-3 text-slate-700">{shortDate(d.date)}</td>
                {METRICS.map((m) => (
                  <td key={m.key} className="px-3 py-2 text-right tabular-nums text-slate-900">
                    {d[m.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const active = METRICS.find((m) => m.key === metric) ?? METRICS[0];

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Activity metric">
        {METRICS.map((m) => {
          const total = data.reduce((a, d) => a + (d[m.key] ?? 0), 0);
          const selected = m.key === metric;
          return (
            <button
              key={m.key}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setMetric(m.key)}
              className={cx(
                "flex items-baseline gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors",
                selected
                  ? "border-slate-300 bg-slate-100 text-slate-900"
                  : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-900",
              )}
            >
              <span className={selected ? "font-medium" : undefined}>{m.title}</span>
              <span className="font-semibold tabular-nums text-slate-900">{total.toLocaleString("en-IN")}</span>
            </button>
          );
        })}
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
            <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
              minTickGap={32}
            />
            <YAxis allowDecimals={false} tick={AXIS_TICK} tickLine={false} axisLine={false} tickCount={4} width={36} />
            <Tooltip
              cursor={{ stroke: "#cbd5e1", strokeWidth: 1 }}
              content={(props) => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload}
                  label={props.label as string | undefined}
                  unit={active.unit}
                />
              )}
            />
            <Area
              type="monotone"
              dataKey={active.key}
              stroke={PRIMARY}
              strokeWidth={2}
              fill={PRIMARY}
              fillOpacity={0.08}
              activeDot={{ r: 4, fill: PRIMARY, stroke: "#fff", strokeWidth: 2 }}
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Single-series histogram of submission scores (percent buckets). */
export function ScoreDistributionChart({ data }: { data: { bucket: string; count: number }[] }) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
          <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
          <XAxis
            dataKey="bucket"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tickFormatter={(b: string) => `${b}%`}
          />
          <YAxis allowDecimals={false} tick={AXIS_TICK} tickLine={false} axisLine={false} tickCount={4} width={36} />
          <Tooltip
            cursor={{ fill: "#f1f5f9" }}
            content={(props) => (
              <ChartTooltip
                active={props.active}
                payload={props.payload}
                label={props.label !== undefined ? `${props.label}%` : undefined}
                unit="submissions"
              />
            )}
          />
          <Bar dataKey="count" fill={PRIMARY} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
