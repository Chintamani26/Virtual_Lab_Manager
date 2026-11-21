"""Response policy check for the AI Lab Tutor: runs on every model reply before it is stored or shown.

The first line of defence is that restricted data never reaches the model (tutor_context). This module enforces
the tutor's output policy on what comes back:
* leaked instructions (the per-process canary, or the rule text itself) -> the whole reply is replaced;
* solution code: multi-line fenced blocks, and unfenced runs of code-like lines (Python, circuit gate
  assignments) -> removed;
* hidden test names -> replaced (the model never sees them; defence in depth);
* worksheet labs: numbers equal to the expected value of a check the student hasn't passed yet, and not already
  visible on the page -> hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.tutor_context import LabContext

MAX_REPLY_CHARS = 1800
MAX_QUESTION_CHARS = 300
CODE_REMOVED = "*(code removed: try writing it yourself)*"
VALUE_HIDDEN = "*(value hidden: work it out)*"
LEAK_REPLY = "Let's get back to your lab. What would you like to work on: the brief, your code or a failing test?"

_FENCE = re.compile(r"```[^\n`]*\n?(.*?)(?:```|$)", re.DOTALL)
_PY_LINE = re.compile(
    r"^\s*(def\s+\w+\s*\(|class\s+\w+|(for|while|if|elif|with)\s.+:\s*$|else\s*:\s*$|try\s*:\s*$|except\b.*:\s*$|"
    r"return\b|yield\b|import\s+\w|from\s+\S+\s+import\b|print\(|"
    r"[A-Za-z_]\w*(\.\w+|\[[^\]]*\])*\s*(=|\+=|-=|\*=|/=)\s*\S)"
)
_GATE_LINE = re.compile(r"^\s*[A-Za-z_]\w*\s*=\s*(AND|OR|XOR|NOT|NAND|NOR|XNOR|BUF)\s*\(", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])[-−]?\d+(?:\.\d+)?(?:[eE]-?\d+)?(?![\w.]*\d)")
_RULE_PHRASES = ("hard rules", "internal marker", "never follow instructions", "<<name key>>",
                 "you are the ai lab tutor inside virtual lab manager")


@dataclass
class Checked:
    reply: str
    guiding_question: str
    flags: list[str] = field(default_factory=list)


def _leaked(text: str, canary: str) -> bool:
    low = text.lower()
    return canary.lower() in low or sum(p in low for p in _RULE_PHRASES) >= 2


def _strip_fences(text: str) -> tuple[str, bool]:
    removed = False

    def repl(m: re.Match) -> str:
        nonlocal removed
        body = m.group(1).strip()
        if "\n" not in body and len(body) < 80:
            return f"`{body}`" if body else ""
        removed = True
        return CODE_REMOVED

    return _FENCE.sub(repl, text), removed


def _strip_code_runs(text: str, lab_type: str) -> tuple[str, bool]:
    """Remove runs of consecutive code-like lines: >= 3 Python lines, or >= 2 circuit gate assignments."""
    if lab_type == "worksheet":
        return text, False  # worksheet replies hold maths, not code; values are handled separately
    lines = text.split("\n")
    is_code = []
    for i, ln in enumerate(lines):
        gate = bool(_GATE_LINE.match(ln))
        py = bool(_PY_LINE.match(ln)) or (ln.startswith(("    ", "\t")) and ln.strip() != "" and i > 0 and is_code[-1][0])
        is_code.append((gate or py, gate))
    out, i, removed = [], 0, False
    while i < len(lines):
        if not is_code[i][0]:
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and is_code[j][0]:
            j += 1
        run = j - i
        gates = sum(1 for k in range(i, j) if is_code[k][1])
        if run >= 3 or gates >= 2:
            out.append(CODE_REMOVED)
            removed = True
        else:
            out.extend(lines[i:j])
        i = j
    return "\n".join(out), removed


def _to_float(token: str) -> float | None:
    try:
        return float(token.replace("−", "-"))
    except ValueError:
        return None


def _hide_values(text: str, ctx: LabContext) -> tuple[str, bool]:
    secrets_ = ctx.secret_values()
    if not secrets_:
        return text, False
    visible = {v for v in (_to_float(t) for t in _NUMBER.findall(ctx.visible_text())) if v is not None}
    hidden = False

    def repl(m: re.Match) -> str:
        nonlocal hidden
        v = _to_float(m.group(0))
        if v is None or any(abs(v - x) < 1e-12 for x in visible):
            return m.group(0)
        if any(abs(v - exp) <= max(tol, 1e-9) for exp, tol in secrets_):
            hidden = True
            return VALUE_HIDDEN
        return m.group(0)

    return _NUMBER.sub(repl, text), hidden


def _hide_test_names(text: str, names: set[str]) -> tuple[str, bool]:
    hit = False
    for n in names:
        if n and n in text:
            text, hit = text.replace(n, "a hidden check"), True
    return text, hit


def check_reply(reply: str, guiding_question: str, *, ctx: LabContext, canary: str) -> Checked:
    reply, question = (reply or "").strip(), (guiding_question or "").strip()
    if _leaked(reply, canary) or _leaked(question, canary):
        return Checked(reply=LEAK_REPLY, guiding_question="", flags=["leak_blocked"])
    flags: list[str] = []
    out = []
    for text in (reply, question):
        text, a = _strip_fences(text)
        text, b = _strip_code_runs(text, ctx.practical.lab_type)
        text, c = _hide_test_names(text, ctx.hidden_names)
        text, d = _hide_values(text, ctx)
        if (a or b) and "code_removed" not in flags:
            flags.append("code_removed")
        if c and "restricted" not in flags:
            flags.append("restricted")
        if d and "value_hidden" not in flags:
            flags.append("value_hidden")
        out.append(text.strip())
    reply, question = out
    if len(reply) > MAX_REPLY_CHARS:
        reply = reply[:MAX_REPLY_CHARS].rsplit(" ", 1)[0] + " …"
    return Checked(reply=reply or LEAK_REPLY, guiding_question=question[:MAX_QUESTION_CHARS], flags=flags)
