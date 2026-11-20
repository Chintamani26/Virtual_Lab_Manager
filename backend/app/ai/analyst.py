"""Conversational HOD analytics: natural-language questions over a computed department snapshot.

Safety by design: the model never writes SQL or touches the database — it only reads an
aggregated JSON snapshot scoped to the HOD's own department.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.schemas import AskResponse, AskTable


class _AskOut(BaseModel):
    answer: str
    highlights: list[str]
    table_columns: list[str]
    table_rows: list[list[str]]


def _fmt(v) -> str | float | int:
    if v is None:
        return "—"
    return v


class HodAnalyst:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def ask(self, question: str, snapshot: dict) -> AskResponse:
        prompt = f"DEPARTMENT SNAPSHOT (JSON):\n{json.dumps(snapshot, default=str)}\n\nHOD QUESTION: {question}"
        out = await self.ai.gemini_json(system=prompts.HOD_ANALYST, prompt=prompt, schema=_AskOut, temperature=0.2)
        if out is not None:
            table = None
            if out.table_columns and out.table_rows:
                width = len(out.table_columns)
                table = AskTable(columns=out.table_columns, rows=[r[:width] for r in out.table_rows[:10]])
            return AskResponse(answer=out.answer, highlights=out.highlights[:4], table=table,
                               model=self.ai.gemini_model, source="gemini")
        return self._fallback(question, snapshot)

    @staticmethod
    def _fallback(question: str, s: dict) -> AskResponse:
        q = question.lower()
        course_codes = {c["code"] for c in s["courses"]}
        course = next((c for c in course_codes if c.lower() in q), None)
        k = s["kpis"]

        def resp(answer: str, highlights: list[str], cols: list[str] | None = None, rows: list[list] | None = None) -> AskResponse:
            table = AskTable(columns=cols, rows=[[_fmt(v) for v in r] for r in rows]) if cols and rows else None
            return AskResponse(answer=answer, highlights=highlights, table=table, model="rules", source="fallback")

        if re.search(r"integrity|cheat|copy|copied|plagiar|ai[- ]generated|malpractice|proctor|flag", q):
            flags = [f for f in s.get("integrity_flags", []) if not course or f["course_code"] == course]
            if not flags:
                return resp("No submissions are currently flagged for academic-integrity review.",
                            ["Proctored labs block copy/paste and record tab switches and typing behaviour."])
            high = [f for f in flags if f["risk_level"] == "high"]
            top = flags[0]
            return resp(
                f"{len(flags)} submission(s) are flagged for integrity review ({len(high)} high risk). Highest: "
                f"{top['student_name']} on {top['course_code']} · {top['practical_title']} — "
                f"{top['ai_likelihood']}% AI/external-code likelihood ({', '.join(top['top_signals'][:2]).lower()}).",
                ["These are indicators, not proof — faculty should review the evidence and talk to the student.",
                 "Open the submission in the Faculty view to see the proctoring timeline."],
                ["Student", "Lab", "Risk", "AI likelihood %", "Top signals"],
                [[f["student_name"], f"{f['course_code']} · {f['practical_title']}", f["risk_level"], f["ai_likelihood"],
                  "; ".join(f["top_signals"][:2])] for f in flags[:10]],
            )
        if re.search(r"risk|struggl|weak|behind|attention", q):
            students = [st for st in s["students"] if st["at_risk"] and (not course or course in st["courses"])]
            scope = f" in {course}" if course else ""
            if not students:
                return resp(f"No students are currently flagged at risk{scope}.", ["At-risk = completion < 60% or average < 50%."])
            return resp(
                f"{len(students)} student(s) are at risk{scope}. Lowest completion: {students[0]['student_name']} "
                f"({students[0]['completion_rate']}% of due labs submitted).",
                ["Consider a mentoring session or lab-extension for these students.",
                 "At-risk = completion < 60% of due labs or average score < 50%."],
                ["Student", "Roll no.", "Completion %", "Avg score %"],
                [[st["student_name"], st["roll_number"], st["completion_rate"], st["avg_score_pct"]] for st in students[:10]],
            )
        if re.search(r"fail|bottleneck|stuck|hard|difficult|common", q):
            b = s["bottleneck_tests"]
            if not b:
                return resp("Not enough test-run data yet to identify bottlenecks.", [])
            top = b[0]
            return resp(
                f"The biggest bottleneck is `{top['test_name']}` in {top['course_code']} · {top['practical_title']}: "
                f"it failed {top['fail_count']} times ({top['fail_rate']}% of runs) and triggered {top['hint_requests']} AI hint requests.",
                ["Consider a 10-minute recap of this concept in the next lab session.",
                 "High hint requests show students are actively working through it with the Socratic tutor."],
                ["Test", "Lab", "Fail rate %", "Fails", "Hints"],
                [[r["test_name"], f"{r['course_code']} · {r['practical_title']}", r["fail_rate"], r["fail_count"], r["hint_requests"]] for r in b[:6]],
            )
        if re.search(r"completion|lowest|submitted|pending|compliance", q):
            ps = sorted(s["practicals"], key=lambda r: r["completion_rate"])
            if course:
                ps = [p for p in ps if p["course_code"] == course]
            if not ps:
                return resp("No published practicals match that question.", [])
            low = ps[0]
            return resp(
                f"Lowest completion: {low['course_code']} · {low['practical_title']} at {low['completion_rate']}% "
                f"({low['submitted']}/{low['enrolled']} students). Department-wide completion is {k['completion_rate']}%.",
                ["Labs that are still open will rise as the due date approaches."],
                ["Course", "Practical", "Due", "Submitted", "Completion %"],
                [[p["course_code"], p["practical_title"], p["due_at"], f"{p['submitted']}/{p['enrolled']}", p["completion_rate"]] for p in ps[:10]],
            )
        if re.search(r"score|average|perform|grade|marks", q):
            cs = [c for c in s["courses"] if c["practicals"]]
            cs.sort(key=lambda c: c["avg_score_pct"] or 0, reverse=True)
            return resp(
                f"Department average score is {k['avg_score_pct']}%. "
                + (f"Best performing course: {cs[0]['code']} ({cs[0]['avg_score_pct']}%)." if cs else ""),
                [f"{k['submissions']} submissions auto-graded so far."],
                ["Course", "Faculty", "Avg score %", "Completion %"],
                [[c["code"], c["faculty_name"], c["avg_score_pct"], c["completion_rate"]] for c in cs],
            )
        if re.search(r"faculty|teacher|assign|professor|workload", q):
            unassigned = [c["code"] for c in s["courses"] if not c["faculty_name"]]
            return resp(
                f"{len(s['faculty'])} faculty members. "
                + (f"Unassigned courses: {', '.join(unassigned)}." if unassigned else "All courses have a faculty member."),
                ["Assign faculty from the Courses table on this dashboard."],
                ["Faculty", "Courses"],
                [[f["name"], ", ".join(f["courses"]) or "—"] for f in s["faculty"]],
            )
        return resp(
            f"{s['department']}: {k['students']} students, {k['practicals']} published practicals, "
            f"{k['completion_rate']}% completion, average score {k['avg_score_pct']}%, "
            f"{k['at_risk_students']} students at risk, {k['ai_hints_served']} AI hints served.",
            ["Try: 'Which lab has the lowest completion rate?'", "Try: 'What is the most common failing test?'",
             "Try: 'Which students are at risk in CS201?'"],
        )
