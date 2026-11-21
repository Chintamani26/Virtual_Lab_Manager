"""Academic-integrity analysis: AI-generated / externally-sourced code detection.

No detector can *prove* code is AI-generated, so this module combines independent evidence and
reports a likelihood with human-readable reasons for faculty review — never an automatic penalty:

1. Behavioural (strongest): proctoring telemetry — code that appeared without being typed in the
   proctored editor, bulk insertions, inhuman typing bursts, blocked paste/copy/devtools attempts,
   focus loss, or a submission made without any proctored session.
2. Content: Gemini stylometric review (or local heuristics) for hallmarks of generated code
   (type hints / structured docstrings beyond course level, narrative comments, typographic
   characters, sudden style shift vs the student's own earlier code).
3. Copying: line-level similarity of the student's contribution against classmates' submissions.
"""

from __future__ import annotations

import ast
import difflib
import json
import re

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.models import (
    LAB_FILENAME,
    ContentAnalysis,
    IntegrityReport,
    IntegritySignal,
    PracticalRecord,
    ProctorEventRecord,
    ProctoringStats,
    ProctorSessionRecord,
    SimilarityResult,
)

MIN_MEASURABLE_NEW_CHARS = 80
MIN_SIMILARITY_CHARS = 300
MIN_SIMILARITY_LINES = 8
MAX_HUMAN_BURST_CPS = 50
MIN_KEYSTROKE_EVIDENCE_CHARS = 200
MAX_CHARS_PER_KEYSTROKE = 3.0

_NARRATIVE = re.compile(
    r"#\s*(step\s*\d|edge case|helper (function|method)|example usage|time complexity|space complexity|"
    r"this (function|method|class)|base case|recursive case|handle the case|main logic)",
    re.IGNORECASE,
)
_TYPOGRAPHIC = re.compile("[—–‘’“”…]")
_STRUCT_DOC = re.compile(r"^\s*(Args|Arguments|Parameters|Returns|Raises|Yields|Examples?):\s*$", re.MULTILINE)


# ---------------------------------------------------------------- text helpers
def _worksheet(files: dict[str, str]) -> dict:
    try:
        data = json.loads(files.get(LAB_FILENAME["worksheet"], "") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _student_cell(key: str, value) -> bool:
    """Worksheet row cells the student typed (apparatus readings are numbers recorded by the instrument)."""
    return isinstance(value, str)


def code_text(lab_type: str, files: dict[str, str]) -> str:
    """The gradable source text of a lab (notebooks: code cells only; worksheets: only the values the student typed,
    one per line, so typing telemetry is compared with what was actually typed)."""
    raw = files.get(LAB_FILENAME[lab_type], "")
    if lab_type == "worksheet":
        data = _worksheet(files)
        steps = data.get("steps") if isinstance(data.get("steps"), dict) else {}
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        values = [str(v) for v in steps.values() if str(v or "").strip()]
        for r in rows:
            if isinstance(r, dict):
                values += [v for k, v in r.items() if _student_cell(k, v) and v.strip()]
        return "\n".join(values)
    if lab_type != "notebook":
        return raw
    try:
        cells = json.loads(raw).get("cells", [])
    except (json.JSONDecodeError, AttributeError):
        return ""
    out = []
    for c in cells:
        if c.get("cell_type") == "code":
            src = c.get("source", "")
            out.append("".join(src) if isinstance(src, list) else src)
    return "\n".join(out)


def new_code_chars(baseline: str, final: str) -> int:
    """Non-whitespace characters on lines added/changed relative to the baseline."""
    a = [ln.strip() for ln in baseline.splitlines()]
    b = [ln.strip() for ln in final.splitlines()]
    total = 0
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            total += sum(len(re.sub(r"\s+", "", ln)) for ln in b[j1:j2])
    return total


def readings_lines(files: dict[str, str]) -> list[str]:
    """A worksheet's instrument readings, one normalised line per row (empty for maths worksheets)."""
    rows = _worksheet(files).get("rows")
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            nums = [f"{k}={v:g}" for k, v in sorted(r.items()) if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if nums:
                out.append(" ".join(nums))
    return out


MIN_SIMILARITY_READINGS = 4


def contribution_lines(text: str, starter: str) -> list[str]:
    """Normalised lines the student wrote (comments/whitespace stripped, starter lines removed)."""

    def norm(ln: str) -> str:
        return re.sub(r"\s+", " ", ln.split("#", 1)[0]).strip()

    starter_set = {norm(ln) for ln in starter.splitlines()}
    return [n for n in (norm(ln) for ln in text.splitlines()) if n and n not in starter_set]


def line_similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < 0.5:  # cheap upper bound: lengths too different to matter
        return 0.0
    return sm.ratio()


# ---------------------------------------------------------------- proctoring summaries
def proctor_summary(sessions: list[ProctorSessionRecord], events: list[ProctorEventRecord]) -> dict:
    def count(t: str) -> int:
        return sum(1 for e in events if e.event_type == t)

    return {
        "sessions": len(sessions),
        "paste_blocked": count("paste_blocked"),
        "copy_blocked": count("copy_blocked") + count("cut_blocked"),
        "focus_lost": count("focus_lost"),
        "time_away_ms": int(sum(int(e.detail.get("duration_ms", 0) or 0) for e in events if e.event_type == "focus_lost")),
        "fullscreen_exits": count("fullscreen_exit"),
        "devtools_blocked": count("devtools_blocked"),
        "large_insertions": count("large_insertion"),
        "breaks": count("break_start"),
        "break_ms": int(sum(int(e.detail.get("duration_ms", 0) or 0) for e in events if e.event_type == "break_end")),
    }


def _stat(s: ProctorSessionRecord, key: str) -> float:
    try:
        return float(s.stats.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- content heuristics (offline)
def heuristic_content(lab_type: str, text: str, reference_texts: list[str]) -> ContentAnalysis:
    score, ind = 0, []
    if lab_type in ("coding", "notebook"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if funcs:
                def annotated(f) -> bool:
                    args = [a for a in f.args.args if a.arg not in ("self", "cls")]
                    return f.returns is not None or any(a.annotation is not None for a in args)

                n_ann = sum(1 for f in funcs if annotated(f))
                ref_uses_hints = any(re.search(r"\)\s*->|def \w+\([^)]*\w+\s*:\s*[A-Za-z_]", r) for r in reference_texts)
                if n_ann >= 2 and n_ann / len(funcs) >= 0.5:
                    score += 10 if ref_uses_hints else 25
                    ind.append(f"Type hints on {n_ann}/{len(funcs)} functions"
                               + ("" if ref_uses_hints else " — not used in the starter or the student's earlier code"))
                documented = sum(1 for f in funcs if ast.get_docstring(f))
                if len(funcs) >= 4 and documented == len(funcs):
                    score += 10
                    ind.append("Every function carries a docstring")
        n_struct = len(_STRUCT_DOC.findall(text))
        if n_struct >= 2:
            score += 20
            ind.append(f"{n_struct} structured docstring sections (Args/Returns) typical of generated code")
    n_narr = len(_NARRATIVE.findall(text))
    if n_narr >= 2:
        score += 15
        ind.append(f"{n_narr} narrative comments (e.g. 'Step 1', 'Edge case', 'Time complexity')")
    n_typo = len(_TYPOGRAPHIC.findall(text))
    if n_typo:
        score += 15
        ind.append(f"{n_typo} typographic character(s) (em dash / curly quotes) rarely typed on a keyboard")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    comments = [ln for ln in lines if ln.strip().startswith("#")]
    if len(comments) >= 6 and len(comments) / max(1, len(lines)) > 0.3:
        score += 10
        ind.append(f"High comment density ({len(comments)}/{len(lines)} lines)")
    return ContentAnalysis(ai_style_score=min(100, score), indicators=ind, model="rules", source="fallback")


# ---------------------------------------------------------------- report assembly (pure)
def build_report(
    *,
    practical: PracticalRecord,
    files: dict[str, str],
    sessions: list[ProctorSessionRecord],
    events: list[ProctorEventRecord],
    content: ContentAnalysis,
    peers: list[tuple[str, str, dict[str, str]]],
) -> IntegrityReport:
    """peers: (submission_id, student_name, files) of classmates' latest submissions."""
    lab = practical.lab_type
    final = code_text(lab, files)
    starter = code_text(lab, practical.starter_files)
    summ = proctor_summary(sessions, events)
    baseline = code_text(lab, sessions[0].baseline_files) if sessions and sessions[0].baseline_files else starter

    typed = int(sum(_stat(s, "typed_chars") for s in sessions))
    large = max(summ["large_insertions"], int(sum(_stat(s, "large_insertions") for s in sessions)))
    large_chars = int(sum(_stat(s, "large_insertion_chars") for s in sessions))
    burst = max((_stat(s, "max_burst_cps") for s in sessions), default=0.0)
    new_chars = new_code_chars(baseline, final)
    measurable = bool(sessions) and new_chars >= MIN_MEASURABLE_NEW_CHARS
    ratio = round(typed / new_chars, 2) if measurable else None

    stats = ProctoringStats(
        proctored=practical.proctored, sessions=summ["sessions"], paste_blocked=summ["paste_blocked"],
        copy_blocked=summ["copy_blocked"], focus_lost=summ["focus_lost"], time_away_ms=summ["time_away_ms"],
        fullscreen_exits=summ["fullscreen_exits"], devtools_blocked=summ["devtools_blocked"], large_insertions=large,
        typed_chars=typed, new_code_chars=new_chars, typed_ratio=ratio, max_burst_cps=round(burst, 1),
    )

    signals: list[IntegritySignal] = []
    behavioural: list[int] = []

    def add(key, label, detail, severity, weight):
        signals.append(IntegritySignal(key=key, label=label, detail=detail, severity=severity, weight=weight))

    if practical.proctored and not sessions:
        add("no_session", "No proctored session",
            "The code was submitted without ever opening the proctored workspace (e.g. via a script or the API).",
            "critical", 30)
        behavioural.append(70)
    if ratio is not None:
        if ratio < 0.3:
            add("typed_ratio", "Answers appeared without being typed" if lab == "worksheet" else "Code appeared without being typed",
                f"Only {typed} characters were typed in the editor, but the submission adds {new_chars} new characters "
                f"({int(ratio * 100)}%).", "critical", 35)
            behavioural.append(90)
        elif ratio < 0.6:
            add("typed_ratio", "Many answers were not typed" if lab == "worksheet" else "Much of the code was not typed",
                f"{typed} characters typed vs {new_chars} new characters in the submission ({int(ratio * 100)}%).",
                "warning", 20)
            behavioural.append(60)
    if large:
        add("large_insertion", "Bulk code insertion",
            f"{large} single edit(s) inserted 60+ characters at once ({large_chars} characters in total) — "
            "typical of pasting or auto-typing tools.", "critical" if large >= 2 else "warning", 25 if large >= 2 else 12)
        behavioural.append(85 if large >= 2 else 60)
    keystrokes = int(sum(_stat(s, "keystrokes") for s in sessions))
    if typed >= MIN_KEYSTROKE_EVIDENCE_CHARS and (keystrokes == 0 or typed / keystrokes > MAX_CHARS_PER_KEYSTROKE):
        per_key = f"{typed / keystrokes:.1f} characters per key" if keystrokes else "no key presses at all"
        add("keystroke_mismatch", "Text entered without typing",
            f"{typed} characters were entered with only {keystrokes} keystrokes ({per_key}; normal typing with "
            "auto-indent is ~1–1.6) — typical of auto-typing tools or injected code.", "critical", 30)
        behavioural.append(85)
    # Weak on its own: auto-indent/autocomplete insert several characters per key, so only extreme bursts count.
    if burst > MAX_HUMAN_BURST_CPS:
        add("typing_burst", "Extremely fast text entry",
            f"Peak of {burst:.0f} characters/second (fast typists sustain ~8–12, briefly more with auto-indent).",
            "warning", 10)
        behavioural.append(40)
    if summ["paste_blocked"]:
        n = summ["paste_blocked"]
        add("paste_attempts", "Paste attempts blocked", f"{n} paste attempt(s) were blocked during the lab.",
            "warning" if n >= 3 else "info", 10 if n >= 3 else 5)
    if summ["copy_blocked"]:
        n = summ["copy_blocked"]
        add("copy_attempts", "Copy attempts blocked",
            f"{n} copy/cut attempt(s) were blocked (possibly to move the task into another tool).",
            "warning" if n >= 3 else "info", 8 if n >= 3 else 3)
    if summ["devtools_blocked"]:
        add("devtools", "Developer-tools shortcuts", f"{summ['devtools_blocked']} attempt(s) to open developer tools.",
            "warning", 10)
    away_min = summ["time_away_ms"] / 60000
    if summ["focus_lost"]:
        n = summ["focus_lost"]
        if n >= 12 or away_min >= 10:
            sev, w = "warning", 15
        elif n >= 5 or away_min >= 3:
            sev, w = "warning", 8
        else:
            sev, w = "info", 2
        add("focus_lost", "Left the lab window", f"Switched away {n} time(s), {away_min:.1f} min in total.", sev, w)
    if summ["breaks"]:
        n, mins = summ["breaks"], summ["break_ms"] / 60000
        add("breaks", "Took declared breaks",
            f"{n} break(s) with the Pause button, {mins:.1f} min in total. Breaks are allowed and are not counted as "
            "leaving the lab.", "info", 0)
    if summ["fullscreen_exits"] >= 3:
        add("fullscreen", "Exited fullscreen", f"Left fullscreen {summ['fullscreen_exits']} times.", "info", 5)

    s = content.ai_style_score
    if s >= 25:
        add("ai_style", "AI-style code patterns",
            "; ".join(content.indicators[:3]) or f"Content analysis score {s}/100.",
            "critical" if s >= 70 else ("warning" if s >= 40 else "info"), round(s * 0.35))

    # copying between students
    sim = SimilarityResult()
    if lab == "worksheet":
        # Correct maths answers are identical for everyone, so only experiment readings are compared: the simulated
        # instruments add random noise, so two students recording the same readings means a copied table.
        mine_r = readings_lines(files)
        if len(mine_r) >= MIN_SIMILARITY_READINGS:
            for sub_id, name, peer_files in peers:
                theirs_r = set(readings_lines(peer_files))
                if len(theirs_r) < MIN_SIMILARITY_READINGS:
                    continue
                r = sum(1 for x in mine_r if x in theirs_r) / len(mine_r)
                if r > sim.max_peer_similarity:
                    sim = SimilarityResult(max_peer_similarity=round(r, 3), peer_submission_id=sub_id,
                                           peer_student_name=name)
            if sim.max_peer_similarity >= 0.8:
                add("peer_similarity", "Same readings as a classmate",
                    f"{int(sim.max_peer_similarity * 100)}% of the recorded readings are identical to "
                    f"{sim.peer_student_name}'s. Each run of the virtual instrument gives slightly different values.",
                    "critical", 30)
    mine = contribution_lines(final, starter) if lab != "worksheet" else []
    if sum(len(x) for x in mine) >= MIN_SIMILARITY_CHARS and len(mine) >= MIN_SIMILARITY_LINES:
        for sub_id, name, peer_files in peers:
            theirs = contribution_lines(code_text(lab, peer_files), starter)
            if sum(len(x) for x in theirs) < MIN_SIMILARITY_CHARS:
                continue
            r = line_similarity(mine, theirs)
            if r > sim.max_peer_similarity:
                sim = SimilarityResult(max_peer_similarity=round(r, 3), peer_submission_id=sub_id, peer_student_name=name)
        if sim.max_peer_similarity >= 0.95:
            add("peer_similarity", "Near-identical to a classmate",
                f"{int(sim.max_peer_similarity * 100)}% of the code lines match {sim.peer_student_name}'s submission.",
                "critical", 30)
        elif sim.max_peer_similarity >= 0.85:
            add("peer_similarity", "Very similar to a classmate",
                f"{int(sim.max_peer_similarity * 100)}% line similarity with {sim.peer_student_name}'s submission.",
                "warning", 15)

    signals.sort(key=lambda x: x.weight, reverse=True)
    risk = min(100, sum(x.weight for x in signals))
    level = "high" if risk >= 60 else ("medium" if risk >= 30 else "low")

    if behavioural:
        b = max(behavioural)
        ai = round(0.7 * max(b, s) + 0.3 * min(b, s))
    elif sessions:
        ai = round(0.7 * s + 0.3 * 10) if s > 10 else s
    else:
        ai = s
    ai = max(0, min(100, ai))

    concerns = [x for x in signals if x.severity != "info"]
    if not concerns:
        if not sessions:
            summary = "No strong integrity concerns detected."
        elif lab == "worksheet":
            summary = "No integrity concerns: the answers were entered in the proctored worksheet."
        else:
            summary = ("No integrity concerns: the code was written in the proctored editor and shows no strong "
                       "AI-generation hallmarks.")
    else:
        summary = (f"{len(concerns)} concern(s): " + "; ".join(x.label for x in concerns[:3])
                   + ". Review the evidence and discuss with the student before taking action.")
    return IntegrityReport(risk_level=level, risk_score=risk, ai_likelihood=ai, summary=summary, signals=signals,
                           proctoring=stats, content=content, similarity=sim)


# ---------------------------------------------------------------- async service (Gemini content review)
class _ContentOut(BaseModel):
    ai_style_score: int
    indicators: list[str]


class IntegrityAnalyzer:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def content(self, practical: PracticalRecord, text: str, reference_texts: list[str]) -> ContentAnalysis:
        heuristic = heuristic_content(practical.lab_type, text, reference_texts)
        if practical.lab_type == "worksheet":
            return heuristic  # numeric answers have no code style to analyse
        numbered = "\n".join(f"{i:>4}| {ln}" for i, ln in enumerate(text.splitlines()[:600], start=1))
        refs = "\n\n---\n\n".join(r[:4000] for r in reference_texts[:2]) or "(none available)"
        prompt = (
            f"COURSE LAB: {practical.title} ({practical.lab_type})\nBRIEF (excerpt):\n{practical.description[:1500]}\n\n"
            f"STUDENT'S EARLIER CODE / STARTER (style reference):\n{refs}\n\n"
            f"SUBMITTED CODE:\n{numbered}\n\n"
            f"Local heuristic indicators (may be incomplete): {heuristic.indicators or 'none'}"
        )
        out = await self.ai.gemini_json(system=prompts.INTEGRITY_REVIEWER, prompt=prompt, schema=_ContentOut,
                                        temperature=0.1, max_tokens=1024)
        if out is None:
            return heuristic
        return ContentAnalysis(ai_style_score=max(0, min(100, out.ai_style_score)), indicators=out.indicators[:5],
                               model=self.ai.gemini_model, source="gemini")

    async def analyze(
        self,
        *,
        practical: PracticalRecord,
        files: dict[str, str],
        sessions: list[ProctorSessionRecord],
        events: list[ProctorEventRecord],
        peers: list[tuple[str, str, dict[str, str]]],
        reference_texts: list[str],
    ) -> IntegrityReport:
        content = await self.content(practical, code_text(practical.lab_type, files), reference_texts)
        return build_report(practical=practical, files=files, sessions=sessions, events=events, content=content,
                            peers=peers)
