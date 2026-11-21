"use client";

import { useEffect, useMemo, useState } from "react";
import { cx } from "@/components/ui";
import { gauss } from "@/lib/worksheet";

const WIRE = "#9aa3b2";

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Digital panel meter. */
function Meter({ label, value, unit, testId }: { label: string; value: string; unit: string; testId: string }) {
  return (
    <div className="rounded-lg border border-line bg-canvas px-3 py-2.5">
      <p className="text-[11px] text-fg-faint">{label}</p>
      <p className="mt-0.5 font-mono text-2xl tabular-nums text-emerald-300" data-testid={testId}>
        {value} <span className="text-sm text-fg-faint">{unit}</span>
      </p>
    </div>
  );
}

/**
 * Virtual DC bench for Ohm's law: variable supply → ammeter → unknown resistor Rₓ, voltmeter across Rₓ.
 * Meter readings carry a little instrument noise; Rₓ glows when it is driven past its power rating.
 */
export function DcBench({
  config,
  onRecord,
  disabled,
  full,
}: {
  config: Record<string, number>;
  onRecord: (row: { V: number; I: number }) => void;
  disabled: boolean;
  full: boolean;
}) {
  const R = config.resistance_ohm ?? 220;
  const rated = config.rated_power_w ?? 0.5;
  const vMax = config.max_voltage_v ?? 12;
  const [on, setOn] = useState(false);
  const [setV, setSetV] = useState(5);
  const [reading, setReading] = useState({ v: 0, i: 0 });

  // a fresh pair of readings every time the circuit changes (instrument noise)
  useEffect(() => {
    if (!on || setV === 0) {
      setReading({ v: 0, i: 0 });
      return;
    }
    const v = Math.round((setV + gauss(0.004)) * 100) / 100;
    const i = Math.round((v / R) * 1000 * (1 + gauss(0.002)) * 10) / 10;
    setReading({ v, i });
  }, [on, setV, R]);

  const power = on ? (setV * setV) / R : 0;
  const hot = power > rated;
  const still = useMemo(() => reducedMotion(), []);
  const canRecord = on && setV > 0 && !disabled && !full;
  const nudge = (d: number) => setSetV((v) => Math.min(vMax, Math.max(0, Math.round((v + d) * 2) / 2)));
  // current flow animation: faster dots for more current
  const flowDur = reading.i > 0 ? Math.max(0.4, 6 / Math.sqrt(reading.i)) : 0;

  return (
    <div className="space-y-4">
      <svg viewBox="0 0 520 210" className="h-auto w-full" role="img" aria-label="Circuit: DC supply, ammeter, resistor Rx and voltmeter">
        {/* main loop */}
        <path id="loop" d="M60 150 V50 H190 M250 50 H330 M410 50 H470 V150 H60" fill="none" stroke={WIRE} strokeWidth="2" />
        {on && reading.i > 0 && !still && (
          <path d="M60 150 V50 H470 V150 H60" fill="none" stroke="#fbbf24" strokeWidth="2.5" strokeDasharray="2 14" strokeLinecap="round">
            <animate attributeName="stroke-dashoffset" from="32" to="0" dur={`${flowDur}s`} repeatCount="indefinite" />
          </path>
        )}
        {/* supply */}
        <circle cx="60" cy="100" r="24" fill="#151821" stroke={WIRE} strokeWidth="2" />
        <text x="60" y="96" fill="#e6e8ee" fontSize="13" textAnchor="middle">+</text>
        <text x="60" y="114" fill="#e6e8ee" fontSize="13" textAnchor="middle">−</text>
        <text x="20" y="190" fill="#9aa3b2" fontSize="11">DC supply 0–{vMax} V</text>
        {/* switch */}
        <circle cx="190" cy="50" r="3" fill={WIRE} />
        <circle cx="250" cy="50" r="3" fill={WIRE} />
        <line x1="190" y1="50" x2={on ? 250 : 240} y2={on ? 50 : 28} stroke={on ? "#34d399" : WIRE} strokeWidth="2.5" />
        <text x="220" y="78" fill="#9aa3b2" fontSize="11" textAnchor="middle">switch</text>
        {/* ammeter */}
        <circle cx="300" cy="50" r="16" fill="#151821" stroke={WIRE} strokeWidth="2" />
        <text x="300" y="55" fill="#e6e8ee" fontSize="13" textAnchor="middle" fontWeight="600">A</text>
        {/* resistor Rx */}
        <rect
          x="330"
          y="38"
          width="80"
          height="24"
          rx="3"
          fill={hot ? "rgba(244,63,94,0.35)" : on ? "rgba(251,191,36,0.12)" : "#151821"}
          stroke={hot ? "#fb7185" : WIRE}
          strokeWidth="2"
        />
        <text x="370" y="55" fill="#e6e8ee" fontSize="13" textAnchor="middle">Rₓ</text>
        {/* voltmeter across Rx */}
        <path d="M330 50 V110 H352 M388 110 H410 V50" fill="none" stroke={WIRE} strokeWidth="1.5" />
        <circle cx="370" cy="110" r="16" fill="#151821" stroke={WIRE} strokeWidth="2" />
        <text x="370" y="115" fill="#e6e8ee" fontSize="13" textAnchor="middle" fontWeight="600">V</text>
        <text x="370" y="20" fill={hot ? "#fb7185" : "#9aa3b2"} fontSize="11" textAnchor="middle">
          {hot ? "overheating" : `rated ${rated} W`}
        </text>
      </svg>

      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-fg-muted">Supply</span>
            <button
              onClick={() => setOn((o) => !o)}
              disabled={disabled}
              aria-pressed={on}
              className={cx("btn h-7 px-2.5 text-xs", on ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-inset ring-emerald-400/30" : "btn-secondary")}
              data-testid="supply-switch"
            >
              {on ? "On" : "Off"}
            </button>
          </div>
          <div>
            <div className="flex items-baseline justify-between">
              <label htmlFor="supply-voltage" className="text-xs text-fg-muted">
                Voltage knob
              </label>
              <span className="font-mono text-sm text-fg">{setV.toFixed(1)} V</span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <button onClick={() => nudge(-0.5)} disabled={disabled} className="btn btn-secondary h-7 w-7 px-0" aria-label="Lower the voltage by 0.5 V">
                −
              </button>
              <input
                id="supply-voltage"
                type="range"
                min={0}
                max={vMax}
                step={0.5}
                value={setV}
                disabled={disabled}
                onChange={(e) => setSetV(Number(e.target.value))}
                className="w-full accent-indigo-500"
              />
              <button onClick={() => nudge(0.5)} disabled={disabled} className="btn btn-secondary h-7 w-7 px-0" aria-label="Raise the voltage by 0.5 V">
                +
              </button>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Meter label="Voltmeter" value={reading.v.toFixed(2)} unit="V" testId="voltmeter" />
          <Meter label="Ammeter" value={reading.i.toFixed(1)} unit="mA" testId="ammeter" />
        </div>
      </div>

      {hot && (
        <p className="rounded-lg border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="status">
          Rₓ is dissipating more than its {rated} W rating and heating up. Lower the voltage to protect it.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => onRecord({ V: reading.v, I: reading.i })}
          disabled={!canRecord}
          className="btn btn-primary"
          data-testid="record-reading"
        >
          Record reading
        </button>
        <p className="text-xs text-fg-faint">
          {full
            ? "The table is full. Remove a reading to take another."
            : on
              ? "Set a voltage, read both meters, then record."
              : "Switch the supply on to start."}
        </p>
      </div>
    </div>
  );
}
