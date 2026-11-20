"""Worksheet labs: step-by-step maths problems and virtual experiments (no code for the student).

Each lab is a brief (markdown), a WorksheetSpec (what the UI renders), test cases (hidden Python checks run in the
sandbox against answers.json via app/execution/service.py WORKSHEET_PRELUDE), a rubric, a reference answer set and
a generator for realistic seeded answers. Check messages guide the student without giving the value away.
"""

from __future__ import annotations

import json
import math
import random

from app.models import (
    RubricCriterion,
    TestCaseSpec,
    TestResult,
    WorksheetColumn,
    WorksheetGraph,
    WorksheetSection,
    WorksheetSpec,
    WorksheetStep,
    WorksheetTable,
)

EMPTY_ANSWERS = json.dumps({"steps": {}, "rows": []})


def _t(name: str, description: str, code: str, hidden: bool = False) -> TestCaseSpec:
    return TestCaseSpec(name=name, description=description, code=code.strip("\n"), hidden=hidden)


def _r(id_: str, name: str, description: str, pts: float) -> RubricCriterion:
    return RubricCriterion(id=id_, name=name, description=description, max_points=pts)


def _step(id_: str, label: str, test: str, unit: str = "", placeholder: str = "") -> WorksheetStep:
    return WorksheetStep(id=id_, label=label, unit=unit, placeholder=placeholder, test=test)


def _value_check(step: str, label: str, expected: float, tol: float, message: str) -> str:
    return f"assert near(answer({step!r}, {label!r}), {expected!r}, {tol!r}), {message!r}"


# =====================================================================================
# MA201 · Applied Mathematics — Newton–Raphson and Simpson's rule (step-by-step problems)
# =====================================================================================
NM_DESCRIPTION = """## Lab 2: Newton–Raphson and Simpson's Rule

Two classic numerical-methods problems, solved **one step at a time**. Open the **Worksheet** tab, enter your answer
for each step and press **Check** to see which steps are right. There is no code to write — just your working.

- Give answers to **at least 4 decimal places** unless a step asks otherwise.
- Use your earlier answers in later steps, exactly as you would on paper.
- The figure next to each problem updates as you enter values, so you can see the method working.
"""

# (step id, label, unit, placeholder, test, description, expected, tolerance, guidance when wrong)
_NM_STEPS = {
    "newton": [
        ("nr_f0", "f(x₀)", "", "", "test_nr_f_x0", "Step 1: f(x₀)", -1.0, 1e-6,
         "Not quite. Substitute x₀ = 2 into x³ − 2x − 5 term by term."),
        ("nr_df0", "f′(x₀)", "", "", "test_nr_df_x0", "Step 2: f′(x₀)", 10.0, 1e-6,
         "Differentiate f(x) first using the power rule, then substitute x₀ = 2."),
        ("nr_x1", "x₁ = x₀ − f(x₀) / f′(x₀)", "", "", "test_nr_x1", "Step 3: x₁", 2.1, 1e-4,
         "Apply the update x₁ = x₀ − f(x₀) / f′(x₀). Watch the sign when f(x₀) is negative."),
        ("nr_f1", "f(x₁)", "", "4 decimal places", "test_nr_f_x1", "Step 4: f(x₁)", 0.061, 5e-4,
         "Evaluate f at your x₁. Keep at least 4 decimal places."),
        ("nr_df1", "f′(x₁)", "", "", "test_nr_df_x1", "Step 5: f′(x₁)", 11.23, 5e-3,
         "Evaluate the derivative from step 2 at your x₁."),
        ("nr_x2", "x₂ = x₁ − f(x₁) / f′(x₁)", "", "4 decimal places", "test_nr_x2", "Step 6: x₂", 2.094568, 1e-4,
         "Apply the same update again, starting from x₁."),
        ("nr_root", "Root correct to 4 decimal places", "", "4 decimal places", "test_nr_root", "Step 7: the root",
         2.0945515, 5e-5, "Iterate until two successive values agree to 4 decimal places, then round."),
    ],
    "simpson": [
        ("sr_h", "Strip width h", "", "", "test_sr_h", "Step 1: h", 0.25, 1e-9,
         "h = (b − a) / n, with a = 0, b = 1 and n = 4."),
        ("sr_ends", "y₀ + y₄", "", "", "test_sr_ends", "Step 2: end ordinates", 1.5, 1e-4,
         "y₀ = f(0) and y₄ = f(1), where f(x) = 1 / (1 + x²)."),
        ("sr_odd", "4 × (y₁ + y₃)", "", "4 decimal places", "test_sr_odd", "Step 3: odd ordinates", 6.324706, 5e-4,
         "The odd ordinates are y₁ = f(0.25) and y₃ = f(0.75). Add them, then multiply by 4."),
        ("sr_even", "2 × y₂", "", "", "test_sr_even", "Step 4: even ordinate", 1.6, 1e-4,
         "The even interior ordinate is y₂ = f(0.5). Multiply it by 2."),
        ("sr_integral", "I ≈ (h / 3) × [(y₀ + y₄) + 4(y₁ + y₃) + 2y₂]", "", "4 decimal places", "test_sr_integral",
         "Step 5: the integral", 0.785392, 5e-5, "Add the three terms from steps 2–4, then multiply by h / 3."),
        ("sr_pi", "π ≈ 4 × I", "", "4 decimal places", "test_sr_pi", "Step 6: estimate of π", 3.141569, 1e-4,
         "The exact value of the integral is π / 4, so multiply your I by 4."),
    ],
}

NM_WORKSHEET = WorksheetSpec(
    kind="problems",
    sections=[
        WorksheetSection(
            id="newton", title="Problem 1 · Newton–Raphson method", visual="newton",
            body="Find the real root of **f(x) = x³ − 2x − 5**, starting from **x₀ = 2**.",
            steps=[_step(s[0], s[1], s[4], s[2], s[3]) for s in _NM_STEPS["newton"]],
        ),
        WorksheetSection(
            id="simpson", title="Problem 2 · Simpson's 1/3 rule", visual="simpson",
            body="Estimate **I = ∫₀¹ dx / (1 + x²)** using **n = 4** strips. The exact value is π / 4, "
                 "so your result also estimates π.",
            steps=[_step(s[0], s[1], s[4], s[2], s[3]) for s in _NM_STEPS["simpson"]],
        ),
    ],
)

NM_TESTS = [
    _t(test, desc, _value_check(step, label, expected, tol, msg))
    for section in _NM_STEPS.values()
    for step, label, _unit, _ph, test, desc, expected, tol, msg in section
]

NM_RUBRIC = [
    _r("correctness", "Correct answers", "Each step's value is correct.", 7),
    _r("precision", "Working and precision", "Every step is answered, to the requested number of decimal places.", 3),
]

NM_REFERENCE = {
    "nr_f0": "-1", "nr_df0": "10", "nr_x1": "2.1", "nr_f1": "0.061", "nr_df1": "11.23", "nr_x2": "2.0946",
    "nr_root": "2.0946", "sr_h": "0.25", "sr_ends": "1.5", "sr_odd": "6.3247", "sr_even": "1.6",
    "sr_integral": "0.7854", "sr_pi": "3.1416",
}
# typical slips, used to make seeded failing submissions look real
_NM_MISTAKES = {
    "test_nr_f_x0": ("nr_f0", "1"), "test_nr_df_x0": ("nr_df0", "12"), "test_nr_x1": ("nr_x1", "1.9"),
    "test_nr_f_x1": ("nr_f1", "0.61"), "test_nr_df_x1": ("nr_df1", "13.23"), "test_nr_x2": ("nr_x2", "2.0457"),
    "test_nr_root": ("nr_root", "2.09"), "test_sr_h": ("sr_h", "0.2"), "test_sr_ends": ("sr_ends", "1"),
    "test_sr_odd": ("sr_odd", "1.5812"), "test_sr_even": ("sr_even", "0.8"), "test_sr_integral": ("sr_integral", "0.7833"),
    "test_sr_pi": ("sr_pi", "3.1333"),
}


def nm_answers(failed: set[str] | frozenset[str] = frozenset()) -> dict:
    steps = dict(NM_REFERENCE)
    for test in failed:
        if test in _NM_MISTAKES:
            key, wrong = _NM_MISTAKES[test]
            steps[key] = wrong
    return {"steps": steps, "rows": []}


# =====================================================================================
# PH101 · Physics — simple pendulum (virtual experiment)
# =====================================================================================
PENDULUM_G = 9.81

PENDULUM_DESCRIPTION = """## Lab 1: Simple Pendulum — Measuring g

**Aim.** Find the acceleration due to gravity, *g*, from the period of a simple pendulum.

**Theory.** For small swings the period is T = 2π √(L / g), so **T² = (4π² / g) · L**. A graph of T² against L is a
straight line through the origin with slope 4π² / g.

**Procedure** (in the **Worksheet** tab)
1. Set the length L with the slider and press **Time 10 oscillations**. The stopwatch stops after 10 full swings.
2. Press **Record reading** to copy L and t₁₀ into the observation table. Take **at least 5 readings** spread over
   **0.4 m or more**.
3. Fill in T = t₁₀ / 10 and T² for each row. The graph of T² against L draws itself as you go.
4. Find the slope from the best-fit line, then g = 4π² / slope, and the percentage error against 9.81 m/s².

Press **Check** at any time to see which parts are right.
"""

PENDULUM_WORKSHEET = WorksheetSpec(
    kind="experiment",
    apparatus="pendulum",
    apparatus_config={"g": PENDULUM_G, "min_length_m": 0.2, "max_length_m": 1.2},
    table=WorksheetTable(
        title="Observation table",
        columns=[
            WorksheetColumn(key="L", label="Length L", unit="m", source="apparatus"),
            WorksheetColumn(key="t10", label="Time for 10 oscillations t₁₀", unit="s", source="apparatus"),
            WorksheetColumn(key="T", label="Period T = t₁₀ / 10", unit="s", test="test_periods"),
            WorksheetColumn(key="T2", label="T²", unit="s²", test="test_t_squared"),
        ],
        min_rows=5, max_rows=10, test="test_readings",
    ),
    graph=WorksheetGraph(title="T² against L", x="L", y="T2", x_label="L (m)", y_label="T² (s²)"),
    sections=[
        WorksheetSection(
            id="analysis", title="Calculations",
            body="Read the slope from two points far apart on the best-fit line.",
            steps=[
                _step("slope", "Slope of the T²–L graph", "test_slope", "s²/m"),
                _step("g", "g = 4π² / slope", "test_g_value", "m/s²", "2 decimal places"),
                _step("percent_error", "Percentage error = |g − 9.81| / 9.81 × 100", "test_percent_error", "%"),
            ],
        )
    ],
)

PENDULUM_TESTS = [
    _t("test_readings", "At least 5 readings at different lengths, spread over 0.4 m or more.", """
readings(5)
L = column("L", "Length")
assert len(set(round(x, 3) for x in L)) >= 5, "Take readings at 5 different lengths (some of yours repeat)"
assert max(L) - min(L) >= 0.4 - 1e-9, "Spread your lengths over at least 0.4 m so the graph is reliable"
"""),
    _t("test_periods", "T is the period of one oscillation for every reading.", """
t10 = column("t10", "t10")
T = column("T", "Period T")
for i, (a, b) in enumerate(zip(T, t10)):
    assert near(a, b / 10, 0.0051), "Reading %d: T is the time for ONE oscillation, but you timed 10" % (i + 1)
"""),
    _t("test_t_squared", "T² is the square of T for every reading.", """
T = column("T", "Period T")
T2 = column("T2", "T squared")
for i, (a, b) in enumerate(zip(T2, T)):
    assert near_rel(a, b * b, 0.01), "Reading %d: T² should be your T multiplied by itself" % (i + 1)
"""),
    _t("test_slope", "The slope matches the best-fit line of your T²–L graph.", """
m, _ = fit_line(column("L", "Length"), column("T2", "T squared"))
s = answer("slope", "Slope")
assert near_rel(s, m, 0.03), "The slope doesn't match your graph. Use two points far apart on the line: (T² change) / (L change)"
"""),
    _t("test_g_value", "g follows from your slope and is physically reasonable.", """
s = answer("slope", "Slope")
g = answer("g", "g")
assert s > 0, "The slope of T² against L must be positive"
assert near_rel(g, 4 * math.pi ** 2 / s, 0.01), "g should follow from your slope, g = 4π² / slope"
assert 9.3 <= g <= 10.3, "g = %.2f m/s² is far from 9.81 m/s². Recheck your readings and slope" % g
"""),
    _t("test_percent_error", "Percentage error against 9.81 m/s².", """
g = answer("g", "g")
pe = answer("percent_error", "Percentage error")
assert near(pe, abs(g - 9.81) / 9.81 * 100, 0.06), "Percentage error = |g − 9.81| / 9.81 × 100, using your g"
"""),
    _t("test_readings_genuine", "Readings come from the apparatus.", """
for i, (L, t10) in enumerate(zip(column("L"), column("t10"))):
    assert near_rel(t10, 20 * math.pi * math.sqrt(L / 9.81), 0.03), "Reading %d does not match the apparatus" % (i + 1)
""", hidden=True),
]

EXPERIMENT_RUBRIC = [
    _r("correctness", "Calculations and result", "Every calculated column and step is correct.", 6),
    _r("observations", "Observations", "At least five readings over a good range, taken from the apparatus.", 2),
    _r("precision", "Units and precision", "Values are given with sensible precision.", 2),
]


def pendulum_reading(rng: random.Random, length: float) -> tuple[float, float]:
    """One stopwatch reading: true 10-swing time plus human reaction error (start + stop)."""
    t10 = 20 * math.pi * math.sqrt(length / PENDULUM_G) + rng.gauss(0, 0.05)
    return round(length, 2), round(t10, 2)


def pendulum_answers(rng: random.Random, failed: set[str] | frozenset[str] = frozenset()) -> dict:
    lengths = sorted(rng.sample([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2], 4 if "test_readings" in failed else 5))
    if lengths[-1] - lengths[0] < 0.4:
        lengths[-1] = round(lengths[0] + 0.5, 1)
    rows = []
    for length in lengths:
        L, t10 = pendulum_reading(rng, length)
        T = round(t10 / 10, 3)
        if "test_periods" in failed:
            T = t10  # forgot to divide by 10
        T2 = round(T * T, 3)
        if "test_t_squared" in failed:
            T2 = round(2 * T, 3)
        rows.append({"L": L, "t10": t10, "T": f"{T}", "T2": f"{T2}"})
    xs, ys = [r["L"] for r in rows], [float(r["T2"]) for r in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    if "test_slope" in failed:
        slope *= 1.05  # misread the line: still a plausible g, but outside the 3% tolerance
    g = 4 * math.pi ** 2 / slope
    if "test_g_value" in failed:
        g = 2 * math.pi ** 2 / slope
    pe = abs(g - PENDULUM_G) / PENDULUM_G * 100
    if "test_percent_error" in failed:
        pe = abs(g - PENDULUM_G)
    steps = {"slope": f"{slope:.4f}", "g": f"{g:.2f}", "percent_error": f"{pe:.2f}"}
    # g is rounded for display; keep the error consistent with the g the student actually wrote down
    if "test_percent_error" not in failed:
        steps["percent_error"] = f"{abs(float(steps['g']) - PENDULUM_G) / PENDULUM_G * 100:.2f}"
    return {"steps": steps, "rows": rows}


# =====================================================================================
# EE210 · Electrical — Ohm's law V–I characteristic (virtual bench)
# =====================================================================================
OHM_RESISTANCE = 220.0
OHM_RATED_POWER = 0.5

OHM_DESCRIPTION = """## Lab 1: Ohm's Law — V–I Characteristic

**Aim.** Verify Ohm's law for an unknown resistor Rₓ and find its resistance from the V–I graph.

**Circuit.** A variable DC supply drives Rₓ. An ammeter in series reads the current *I* (mA) and a voltmeter across
Rₓ reads the voltage *V*. The resistor is rated **0.5 W**: watch for it overheating at high voltages.

**Procedure** (in the **Worksheet** tab)
1. Switch the supply on and set a voltage with the knob. Read both meters.
2. Press **Record reading** to copy V and I into the observation table. Take **at least 5 readings** spread over
   **4 V or more**.
3. Fill in R = V / I for each row (careful with units: I is in mA). The V–I graph draws itself.
4. Find R from the slope of the graph, then answer the power questions.

Press **Check** at any time to see which parts are right.
"""

OHM_WORKSHEET = WorksheetSpec(
    kind="experiment",
    apparatus="dc_bench",
    apparatus_config={"resistance_ohm": OHM_RESISTANCE, "rated_power_w": OHM_RATED_POWER, "max_voltage_v": 12.0},
    table=WorksheetTable(
        title="Observation table",
        columns=[
            WorksheetColumn(key="V", label="Voltage V", unit="V", source="apparatus"),
            WorksheetColumn(key="I", label="Current I", unit="mA", source="apparatus"),
            WorksheetColumn(key="R", label="R = V / I", unit="Ω", test="test_r_column"),
        ],
        min_rows=5, max_rows=10, test="test_readings",
    ),
    graph=WorksheetGraph(title="V against I", x="I", y="V", x_label="I (mA)", y_label="V (V)"),
    sections=[
        WorksheetSection(
            id="analysis", title="Calculations",
            body="The slope of the V–I graph is the resistance. Take care with units: the graph's current axis is in mA.",
            steps=[
                _step("r_graph", "R from the slope of the V–I graph", "test_r_from_graph", "Ω"),
                _step("r_mean", "Mean of your R = V / I column", "test_r_mean", "Ω"),
                _step("p_9v", "Power dissipated at 9 V, P = V² / R (use R from the graph)", "test_power", "W"),
                _step("v_max", "Highest safe voltage for this 0.5 W resistor", "test_max_voltage", "V"),
            ],
        )
    ],
)

OHM_TESTS = [
    _t("test_readings", "At least 5 readings at different voltages, spread over 4 V or more.", """
readings(5)
V = column("V", "Voltage")
I = column("I", "Current")
assert all(i > 0 for i in I), "Every reading needs a current above 0 mA. Switch the supply on before recording"
assert len(set(round(v, 1) for v in V)) >= 5, "Take readings at 5 different supply voltages"
assert max(V) - min(V) >= 4 - 1e-9, "Spread your readings over at least 4 V"
"""),
    _t("test_r_column", "R = V / I is correct for every reading.", """
V = column("V", "Voltage")
I = column("I", "Current")
R = column("R", "R = V / I")
for k, (r, v, i) in enumerate(zip(R, V, I)):
    if i > 0 and near_rel(r, v / i, 0.01):
        raise AssertionError("Reading %d: you divided by the current in mA. Convert I to amperes first" % (k + 1))
    assert i > 0 and near_rel(r, v / (i / 1000), 0.01), "Reading %d: R should be V divided by I" % (k + 1)
"""),
    _t("test_r_from_graph", "R from the slope of your V–I graph.", """
m, _ = fit_line([i / 1000 for i in column("I", "Current")], column("V", "Voltage"))
r = answer("r_graph", "R from the graph")
if near_rel(r, m / 1000, 0.03):
    raise AssertionError("Your slope is in volts per milliampere (kΩ). Convert it to ohms")
assert near_rel(r, m, 0.03), "R is the slope of your V–I graph: change in V / change in I, with I in amperes"
"""),
    _t("test_r_mean", "Mean of the R column.", """
R = column("R", "R = V / I")
r = answer("r_mean", "Mean resistance")
assert near_rel(r, sum(R) / len(R), 0.005), "Add up your R column and divide by the number of readings"
"""),
    _t("test_power", "Power at 9 V.", """
r = answer("r_graph", "R from the graph")
p = answer("p_9v", "Power at 9 V")
assert near_rel(p, 81 / r, 0.02), "Use P = V² / R with V = 9 V and your R from the graph (P is in watts)"
"""),
    _t("test_max_voltage", "Highest safe voltage for a 0.5 W rating.", """
r = answer("r_graph", "R from the graph")
v = answer("v_max", "Highest safe voltage")
assert near_rel(v, math.sqrt(0.5 * r), 0.02), "Start from P = V² / R with P = 0.5 W and rearrange for V"
"""),
    _t("test_readings_genuine", "Readings come from the bench meters.", """
for k, (v, i) in enumerate(zip(column("V"), column("I"))):
    assert near_rel(i, v / 220.0 * 1000, 0.03), "Reading %d does not match the bench meters" % (k + 1)
""", hidden=True),
    _t("test_r_accuracy", "R is within 3% of the resistor's true value.", """
assert near_rel(answer("r_graph"), 220.0, 0.03), "R is more than 3% away from the resistor's true value"
""", hidden=True),
]


def ohm_reading(rng: random.Random, volts: float) -> tuple[float, float]:
    """Meter readings: voltmeter to 0.01 V, ammeter to 0.1 mA, each with a little noise."""
    v = round(volts + rng.gauss(0, 0.004), 2)
    i = round(v / OHM_RESISTANCE * 1000 * (1 + rng.gauss(0, 0.002)), 1)
    return v, i


def ohm_answers(rng: random.Random, failed: set[str] | frozenset[str] = frozenset()) -> dict:
    volts = sorted(rng.sample([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], 4 if "test_readings" in failed else 5))
    if volts[-1] - volts[0] < 4:
        volts[-1] = volts[0] + 5
    rows = []
    for target in volts:
        v, i = ohm_reading(rng, target)
        r = v / (i / 1000)
        if "test_r_column" in failed:
            r = v / i  # forgot mA -> A
        rows.append({"V": v, "I": i, "R": f"{r:.1f}" if r > 10 else f"{r:.4f}"})
    xs, ys = [row["I"] / 1000 for row in rows], [row["V"] for row in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    r_graph = slope / 1000 if "test_r_from_graph" in failed else slope
    rs = [float(row["R"]) for row in rows]
    r_mean = sum(rs) / len(rs) * (1.1 if "test_r_mean" in failed else 1)
    p = 9 / r_graph if "test_power" in failed else 81 / r_graph
    vmax = 0.5 * r_graph if "test_max_voltage" in failed else math.sqrt(0.5 * r_graph)
    steps = {"r_graph": f"{r_graph:.1f}" if r_graph > 10 else f"{r_graph:.4f}",
             "r_mean": f"{r_mean:.1f}" if r_mean > 10 else f"{r_mean:.5f}",
             "p_9v": f"{p:.4f}", "v_max": f"{vmax:.2f}"}
    return {"steps": steps, "rows": rows}


# =====================================================================================
# registry used by the seed and the tests
# =====================================================================================
def evaluate(tests: list[TestCaseSpec], answers: dict) -> list[TestResult]:
    """Run worksheet checks in-process. ONLY for answers this module generated (seed data); student answers always
    go through the sandboxed ExecutionService."""
    from app.execution.service import WORKSHEET_PRELUDE

    base: dict = {"__name__": "__seed__"}
    exec(WORKSHEET_PRELUDE.replace("__ANSWERS__", repr(json.dumps(answers))), base)  # noqa: S102 - trusted seed data
    out = []
    for t in tests:
        ns = dict(base)
        try:
            exec(t.code or "", ns)  # noqa: S102 - our own check code on our own generated answers
            out.append(TestResult(name=t.name, passed=True, hidden=t.hidden))
        except AssertionError as e:
            out.append(TestResult(name=t.name, passed=False, hidden=t.hidden, message=f"AssertionError: {e}"))
    return out


def seed_answers(slug: str, rng: random.Random, failed: set[str] | frozenset[str] = frozenset()) -> dict:
    if slug == "numerical_methods":
        return nm_answers(failed)
    if slug == "pendulum":
        return pendulum_answers(rng, failed)
    if slug == "ohms_law":
        return ohm_answers(rng, failed)
    raise KeyError(slug)


# Socratic hints (three levels: concept, edge case, logic) used when Gemini is not configured.
CURATED_HINTS: dict[str, list[tuple[str, str, str]]] = {
    "test_nr_df_x0": [
        ("Derivative before substitution",
         "f′(x₀) is the slope of the curve at x₀. You need the derivative function first, then the value at x₀ = 2.",
         "What is the derivative of x³, and of −2x?"),
        ("Power rule",
         "Differentiate term by term: xⁿ becomes n·xⁿ⁻¹, a constant times x becomes the constant, and a constant "
         "becomes 0.", "Which term of x³ − 2x − 5 disappears when you differentiate?"),
        ("Substitute carefully",
         "Write f′(x) out in full, then replace every x with 2. Square before multiplying.",
         "What is 3 × 2² − 2?"),
    ],
    "test_nr_x1": [
        ("Newton–Raphson update",
         "The next estimate is where the tangent at x₀ crosses the x-axis: x₁ = x₀ − f(x₀) / f′(x₀).",
         "Is f(x₀) positive or negative here?"),
        ("Signs",
         "Subtracting a negative number adds. With f(x₀) negative and f′(x₀) positive, x₁ should be to the right of "
         "x₀. Look at the figure: does your x₁ land where the tangent meets the axis?",
         "Should x₁ be larger or smaller than 2?"),
        ("Check with the figure",
         "Compute f(x₀) / f′(x₀) on its own first, then subtract it from x₀.", "What is −1 / 10?"),
    ],
    "test_sr_odd": [
        ("Simpson's weights",
         "Simpson's 1/3 rule weights the ordinates 1, 4, 2, 4, 1. The odd-numbered ones (y₁, y₃) get weight 4.",
         "At which x-values are y₁ and y₃ taken when h = 0.25?"),
        ("Evaluate the function",
         "y₁ = 1 / (1 + 0.25²) and y₃ = 1 / (1 + 0.75²). Square first, add 1, then take the reciprocal.",
         "What is 0.75²?"),
        ("Combine",
         "Add y₁ and y₃, then multiply the sum by 4. Keep 4 decimal places until the very end.",
         "Did you multiply the sum, or only one of the terms?"),
    ],
    "test_periods": [
        ("Period of one swing",
         "The stopwatch measured 10 complete oscillations. The period T is the time for just one.",
         "If 10 swings take 15 s, how long does one take?"),
        ("Why time 10 swings",
         "Timing many swings and dividing reduces the effect of your reaction time on each reading.",
         "What do you divide t₁₀ by?"),
        ("Row by row", "Do the same division for every row of the table.", "Have you updated every row?"),
    ],
    "test_slope": [
        ("Slope of a straight line",
         "The slope is the change in T² divided by the change in L, read from the best-fit line, not from one row.",
         "Which two points on the line are far apart?"),
        ("Use the line, not the points",
         "Pick two points on the drawn line near its ends. Points far apart give a more accurate slope.",
         "What are T² and L at each end of the line?"),
        ("Units", "Slope = (T²₂ − T²₁) / (L₂ − L₁), in s² per metre. It should be about 4.", "Is your slope close to 4?"),
    ],
    "test_r_column": [
        ("Units in Ohm's law",
         "R = V / I works when V is in volts and I in amperes. The ammeter reads milliamperes.",
         "How many milliamperes are in one ampere?"),
        ("Convert first",
         "Divide the current by 1000 to get amperes, then divide V by that.",
         "What is 45.5 mA in amperes?"),
        ("Sanity check", "The resistor is a few hundred ohms. If your R is below 1, a conversion is missing.",
         "Is your R in the hundreds?"),
    ],
    "test_r_from_graph": [
        ("Slope is resistance",
         "On a V–I graph the slope ΔV / ΔI is the resistance, as long as I is in amperes.",
         "What units does the graph's current axis use?"),
        ("Convert the slope",
         "A slope read in volts per milliampere is in kilo-ohms. Multiply by 1000 to get ohms.",
         "Is your answer in the hundreds of ohms?"),
        ("Two points far apart", "Use two points near the ends of the line, then convert.", "What is ΔV and ΔI?"),
    ],
}
