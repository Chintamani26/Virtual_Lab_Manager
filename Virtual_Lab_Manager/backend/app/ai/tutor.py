"""Socratic tutor: progressive hints for the student's failing tests (never full solutions)."""

from __future__ import annotations

import re

from pydantic import BaseModel

from app import worksheet_labs
from app.ai import prompts
from app.ai.client import AIClient
from app.models import ExecutionLogRecord, HintLogRecord, PracticalRecord
from app.schemas import HintResponse

MAX_LEVEL = 3
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)


class _HintOut(BaseModel):
    hint: str
    guiding_question: str
    concept: str
    focus_test: str


# Curated fallback hints for the seeded labs (also a good few-shot reference for prompt design).
CURATED: dict[str, list[tuple[str, str, str]]] = {
    "test_duplicate_keys": [
        ("BST invariant for equal keys",
         "Your tree grows when the same key is inserted twice. Look at `insert()` — every comparison sends a key "
         "either left or right. What *should* happen when the key you are inserting is already in the tree?",
         "If you insert 8 twice, how many nodes should the tree contain?"),
        ("Three-way comparison",
         "Trace `insert(3)` when 3 already exists: your condition only checks `key < node.key`, so an equal key "
         "falls into the `else` branch and is treated like a *larger* key — a new node appears in the right subtree "
         "and `_size` increases. Which case is your comparison missing?",
         "How many different outcomes can comparing two keys have?"),
        ("Handle equality explicitly",
         "Split the decision into three cases: smaller → go left, larger → go right, equal → stop immediately "
         "without creating a node *and* without touching the size counter. Then re-run the tests.",
         "Where exactly will you return early, and which counter must stay unchanged?"),
    ],
    "test_only_cin": [
        ("Carry-in path",
         "With A=0, B=0 and CIN=1 the sum should be 1. Which of your gates ever looks at `CIN`?",
         "In a full adder, how many inputs contribute to SUM?"),
        ("Two half adders",
         "Your SUM only combines A and B. A full adder adds the carry-in in a *second* stage — the result of the "
         "first half adder becomes an input to the next one.",
         "What signal should the second XOR receive besides CIN?"),
        ("Compose the stages",
         "Create an intermediate wire for the first half adder's sum, then XOR it with CIN for the final SUM. "
         "COUT must be 1 if either half adder produces a carry.",
         "Which gate merges the two possible carries?"),
    ],
    "test_median_score": [
        ("Data types",
         "Your median doesn't match. Values read by `csv.DictReader` — what Python type are they?",
         "What is the median of the strings '9' and '10'?"),
        ("Convert before aggregating",
         "Sorting strings compares them character by character, so '100' < '29'. Convert the `score` column to "
         "numbers before calling statistics functions.",
         "Where is the best place to convert — once, or in every task?"),
        ("Build a numeric list",
         "Build one list of integer scores from `rows`, then compute both mean and median from that list.",
         "Does your mean still match after the conversion?"),
    ],
}
CURATED.update(worksheet_labs.CURATED_HINTS)


def _scrub(text: str) -> str:
    """Remove multi-line code blocks the model may have produced despite instructions."""

    def repl(m: re.Match) -> str:
        body = m.group(0).strip("`").strip()
        return m.group(0) if body.count("\n") <= 1 and len(body) < 80 else "*(code removed — try writing it yourself!)*"

    return _CODE_BLOCK.sub(repl, text).strip()


def _unanswered(message: str | None) -> bool:
    """A worksheet check that failed only because the student hasn't filled it in yet."""
    m = (message or "").removeprefix("AssertionError: ")
    return m.endswith(" is empty") or m.startswith(("No readings recorded yet", "Record at least"))


def _test_code(practical: PracticalRecord, name: str) -> str:
    spec = next((t for t in practical.test_cases if t.name == name and not t.hidden), None)
    if spec is None:
        return ""
    if practical.lab_type == "worksheet":
        # a worksheet check's code contains the expected value: describe it instead, so it can't leak into a hint
        return f"(worksheet check) {spec.description}"
    if spec.code:
        return spec.code
    return f"inputs={spec.inputs} expected={spec.expected}"


class SocraticTutor:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    @staticmethod
    def log_record(practical_id: str, student_id: str, execution: ExecutionLogRecord | None, resp: HintResponse,
                   question: str | None) -> HintLogRecord | None:
        """The ai_hint_logs row for a served hint (None when it wasn't about a failing test). Hint levels and the
        HOD hint analytics are computed from these rows."""
        if resp.focus_test is None:
            return None
        return HintLogRecord(
            practical_id=practical_id, student_id=student_id, execution_id=execution.id if execution else None,
            focus_test=resp.focus_test, hint_level=resp.hint_level, question=question,
            hint_text=resp.hint, model=resp.model, source=resp.source,
        )

    @staticmethod
    def next_level(previous: list[HintLogRecord], focus_test: str | None) -> int:
        same = [h for h in previous if h.focus_test == focus_test]
        return min(MAX_LEVEL, len(same) + 1)

    async def hint(
        self,
        *,
        practical: PracticalRecord,
        execution: ExecutionLogRecord | None,
        previous: list[HintLogRecord],
        question: str | None,
    ) -> HintResponse:
        worksheet = practical.lab_type == "worksheet"
        if execution is None:
            return HintResponse(
                hint=("Check your answers first (**Check answers**) so I can see which steps need work, then ask me again."
                      if worksheet else
                      "Run your tests first (**Run Tests**) so I can see what is failing — then ask me again."),
                guiding_question="Which behaviour in the brief do you think is the trickiest?",
                concept="Test-driven debugging", hint_level=1, focus_test=None,
                model="rules", source="fallback",
            )

        failing = [t for t in execution.test_results if not t.passed]
        if not failing and worksheet:
            return HintResponse(
                hint="Every check passes. Before submitting, make sure each answer has sensible precision and units, "
                "and that your readings cover the range the procedure asks for.",
                guiding_question="If you repeated the experiment, which reading would you trust least, and why?",
                concept="Reviewing your work", hint_level=1, focus_test=None, model="rules", source="fallback",
            )
        if not failing:
            return HintResponse(
                hint="All visible tests pass — nice work! Before submitting, think about the edge cases hidden tests "
                "might check (empty input, extremes, repeated values) and tidy up names and comments.",
                guiding_question="What is the smallest and the most extreme input your code could receive?",
                concept="Edge cases & code quality", hint_level=1, focus_test=None,
                model="rules", source="fallback",
            )

        focus = failing[0]
        if worksheet:
            # hint at the first step the student answered wrongly; blank steps only once nothing else is wrong
            attempted = [t for t in failing if not _unanswered(t.message)]
            focus = attempted[0] if attempted else failing[0]
        level = self.next_level(previous, focus.name)
        prior = [h.hint_text for h in previous if h.focus_test == focus.name][-2:]
        files_text = "\n\n".join(f"### {name}\n{src[:12_000]}" for name, src in execution.files.items())

        prompt = (
            ("LAB TYPE: worksheet. The student enters numeric answers and readings, not code. Hint about the maths "
             "or physics, never state the expected value.\n" if worksheet else "")
            + f"LAB: {practical.title}\nBRIEF:\n{practical.description[:3000]}\n\n"
            f"STUDENT FILES:\n{files_text}\n\n"
            f"FAILING TESTS ({len(failing)} of {execution.tests_total}):\n"
            + "\n".join(f"- {t.name}: {t.message}" for t in failing[:5])
            + f"\n\nFOCUS TEST: {focus.name}\nFOCUS TEST CODE:\n{_test_code(practical, focus.name)}\n"
            f"STDERR (tail):\n{execution.stderr[-1500:]}\n\n"
            f"HINT LEVEL: {level} of {MAX_LEVEL}\n"
            f"PREVIOUS HINTS (do not repeat):\n" + ("\n".join(f"- {p}" for p in prior) or "- none")
            + f"\n\nSTUDENT QUESTION: {question or '(none)'}"
        )
        out = await self.ai.gemini_json(system=prompts.SOCRATIC_TUTOR, prompt=prompt, schema=_HintOut, temperature=0.4)
        if out is not None:
            return HintResponse(
                hint=_scrub(out.hint), guiding_question=out.guiding_question, concept=out.concept,
                hint_level=level, focus_test=focus.name, model=self.ai.gemini_model, source="gemini",
            )
        return self._fallback(focus.name, focus.message or "", level, practical)

    @staticmethod
    def _fallback(test_name: str, message: str, level: int, practical: PracticalRecord) -> HintResponse:
        if test_name in CURATED:
            concept, hint, question = CURATED[test_name][level - 1]
        elif practical.lab_type == "worksheet":
            spec = next((t for t in practical.test_cases if t.name == test_name), None)
            what = spec.description if spec else "this step"
            detail = message.removeprefix("AssertionError: ")[:200]
            if _unanswered(message):
                concept = "Where to start"
                hint = (f"**{what}** isn't answered yet. Work through the steps in order: each one uses results "
                        "from the steps before it.")
                question = "Which earlier result does this step need?"
            elif level == 1:
                concept = "Re-read the step"
                hint = f"Look again at **{what}**. {detail}"
                question = "Which formula or reading does this step depend on?"
            elif level == 2:
                concept = "Check your inputs"
                hint = ("This step uses values from earlier steps or from your observation table. Check those first: "
                        "a slip there carries through to here.")
                question = "Is every value you used here already marked correct?"
            else:
                concept = "Units and rounding"
                hint = ("Work the step again on paper, writing the units next to every number. Convert units before "
                        "you divide, and round only at the end.")
                question = "Are all your quantities in the units the step asks for?"
        else:
            spec = next((t for t in practical.test_cases if t.name == test_name), None)
            desc = spec.description if spec else ""
            concept = "Reading the failing test"
            if level == 1:
                hint = (f"Focus on `{test_name}`" + (f" — {desc.rstrip('.')}" if desc else "") + ". What input does this test use, "
                        "and what result does it expect? Walk through your code by hand with exactly that input.")
                question = "At which step does your code's behaviour first differ from the expectation?"
            elif level == 2:
                concept = "Localise the bug"
                hint = (f"The failure message is: `{message[:200]}`. Find the function that produces this value and "
                        "compare each branch against the brief. Which condition handles this scenario?")
                question = "Which branch runs for this input — and is it the right one?"
            else:
                concept = "Fix and verify"
                hint = ("Add a temporary `print` inside the function that handles this case, run with the test's input, "
                        "and compare each intermediate value with what the brief requires. Fix the first divergence, then "
                        "re-run all tests to make sure nothing else broke.")
                question = "Which intermediate value is the first one that's wrong?"
        return HintResponse(
            hint=hint, guiding_question=question, concept=concept, hint_level=level,
            focus_test=test_name, model="rules", source="fallback",
        )
