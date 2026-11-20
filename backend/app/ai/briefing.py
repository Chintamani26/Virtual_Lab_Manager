"""HOD weekly department briefing: Gemini writes the narrative from computed week-over-week metrics.

The metrics (app/services/insights.weekly_metrics) are returned next to the text, so every claim can be checked.
Without Gemini the briefing is assembled from the same metrics by rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.schemas import BriefingAction, DepartmentBriefingOut


class _Action(BaseModel):
    action: str
    owner: str
    reason: str


class _Brief(BaseModel):
    headline: str
    highlights: list[str]
    concerns: list[str]
    actions: list[_Action]


def _delta(now: float | int | None, before: float | int | None) -> str:
    if now is None or before is None:
        return ""
    diff = now - before
    return "no change" if diff == 0 else f"{'up' if diff > 0 else 'down'} {abs(round(diff, 1)):g} from last week"


def rule_based(m: dict) -> _Brief:
    tw, lw = m["this_week"], m["last_week"]
    highlights = [f"{tw['submissions']} submissions this week ({_delta(tw['submissions'], lw['submissions'])}).",
                  f"{tw['active_students']} of {m['students']} students were active "
                  f"({_delta(tw['active_students'], lw['active_students'])})."]
    if tw["avg_score_pct"] is not None:
        highlights.append(f"Average score of this week's submissions: {tw['avg_score_pct']}%.")
    concerns, actions = [], []
    pending = sum(r["pending_reviews"] for r in m["pending_reviews"])
    if pending:
        top = m["pending_reviews"][0]
        concerns.append(f"{pending} submissions are waiting for faculty review (most in {top['course']}, oldest "
                        f"{top['oldest_days']} days).")
        actions.append(_Action(action=f"Review the {top['pending_reviews']} pending {top['course']} submissions",
                               owner=top["faculty"], reason="Students are waiting for feedback."))
    if m["practicals_behind"]:
        b = m["practicals_behind"][0]
        concerns.append(f"{b['course']} '{b['practical']}' is at {b['completion_pct']}% completion ({b['status']}).")
        actions.append(_Action(action=f"Follow up on {b['course']} '{b['practical']}' completion", owner=b["faculty"],
                               reason=f"Only {b['completion_pct']}% of students have submitted."))
    if m["at_risk_students"]["count"]:
        concerns.append(f"{m['at_risk_students']['count']} students are at risk (low completion or score).")
        actions.append(_Action(action="Meet the at-risk students' mentors", owner="HOD",
                               reason=f"{m['at_risk_students']['count']} students need early support."))
    if m["top_bottlenecks"]:
        t = m["top_bottlenecks"][0]
        concerns.append(f"`{t['test']}` in {t['course']} fails in {t['fail_rate_pct']}% of test runs.")
    if m["unassigned_courses"]:
        actions.append(_Action(action=f"Assign faculty to {', '.join(m['unassigned_courses'])}", owner="HOD",
                               reason="These courses have no faculty."))
    headline = concerns[0] if concerns else highlights[0]
    return _Brief(headline=headline, highlights=highlights[:4], concerns=concerns[:4], actions=actions[:4])


def briefing_markdown(b: DepartmentBriefingOut, department: str) -> str:
    lines = [f"# Weekly briefing: {department}", f"*{b.metrics.get('period', '')}*", f"**{b.headline}**"]
    if b.highlights:
        lines.append("## Highlights\n" + "\n".join(f"- {x}" for x in b.highlights))
    if b.concerns:
        lines.append("## Needs attention\n" + "\n".join(f"- {x}" for x in b.concerns))
    if b.actions:
        lines.append("## Recommended actions\n" + "\n".join(f"- **{a.action}** ({a.owner}): {a.reason}" for a in b.actions))
    return "\n\n".join(lines) + "\n"


class DepartmentBriefingGenerator:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def generate(self, metrics: dict, now: datetime) -> DepartmentBriefingOut:
        out = None
        if self.ai.enabled:
            out = await self.ai.gemini_json(system=prompts.DEPARTMENT_BRIEFING,
                                            prompt="METRICS (JSON):\n" + json.dumps(metrics, default=str, ensure_ascii=False),
                                            schema=_Brief, temperature=0.3, max_tokens=2048, timeout_s=45)
        source = "gemini" if out is not None and out.headline.strip() else "fallback"
        b = out if source == "gemini" else rule_based(metrics)

        def clean(xs: list[str], n: int) -> list[str]:
            return [x.strip()[:300] for x in xs if x.strip()][:n]

        result = DepartmentBriefingOut(
            period_start=now - timedelta(days=7), period_end=now, headline=b.headline.strip()[:300],
            highlights=clean(b.highlights, 4), concerns=clean(b.concerns, 4),
            actions=[BriefingAction(action=a.action.strip()[:200], owner=a.owner.strip()[:80], reason=a.reason.strip()[:300])
                     for a in b.actions if a.action.strip()][:4],
            metrics=metrics, markdown="", generated_at=now,
            model=self.ai.gemini_model if source == "gemini" else "rules", source=source,  # type: ignore[arg-type]
        )
        result.markdown = briefing_markdown(result, metrics.get("department", "Department"))
        return result
