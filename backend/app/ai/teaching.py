"""Faculty: teaching material (lecture notes, worked examples, discussion and viva questions) for a topic.

Generated on request and returned as structured sections plus one markdown document for download. Nothing is
stored: the faculty member reviews it and decides what to use.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.ai.practical_gen import AIUnavailable
from app.models import CourseRecord
from app.schemas import MaterialSection, TeachingMaterialOut, TeachingMaterialRequest, VivaItem


class _Section(BaseModel):
    heading: str
    content: str


class _Viva(BaseModel):
    question: str
    answer: str


class _Material(BaseModel):
    title: str
    overview: str
    learning_outcomes: list[str]
    sections: list[_Section]
    examples: list[_Section]
    real_world_examples: list[str]
    common_mistakes: list[str]
    discussion_questions: list[str]
    viva_questions: list[_Viva]


def _items(xs: list[str], n: int, cap: int = 400) -> list[str]:
    return [x.strip()[:cap] for x in xs if x and x.strip()][:n]


def _sections(xs: list[_Section], n: int) -> list[MaterialSection]:
    return [MaterialSection(heading=s.heading.strip()[:160], content=s.content.strip()[:4000])
            for s in xs if s.heading.strip() and s.content.strip()][:n]


def material_markdown(m: TeachingMaterialOut, level: str) -> str:
    def bullets(xs: list[str]) -> str:
        return "\n".join(f"- {x}" for x in xs)

    out = [f"# {m.title}", f"*Level: {level}*", m.overview]
    if m.learning_outcomes:
        out.append("## Learning outcomes\n" + bullets(m.learning_outcomes))
    out += [f"## {s.heading}\n\n{s.content}" for s in m.sections]
    if m.examples:
        out.append("## Worked examples\n\n" + "\n\n".join(f"### {e.heading}\n\n{e.content}" for e in m.examples))
    if m.real_world_examples:
        out.append("## Real-world applications\n" + bullets(m.real_world_examples))
    if m.common_mistakes:
        out.append("## Common mistakes\n" + bullets(m.common_mistakes))
    if m.discussion_questions:
        out.append("## Discussion questions\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(m.discussion_questions, 1)))
    if m.viva_questions:
        out.append("## Viva questions\n" + "\n".join(f"{i}. **{v.question}**  \n   {v.answer}"
                                                     for i, v in enumerate(m.viva_questions, 1)))
    return "\n\n".join(out) + "\n"


class TeachingMaterialGenerator:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def generate(self, req: TeachingMaterialRequest, course: CourseRecord | None) -> TeachingMaterialOut:
        if not self.ai.enabled:
            raise AIUnavailable("Teaching material needs Gemini (GEMINI_API_KEY).")
        request = (
            f"Topic: {req.topic}\nStudent level: {req.level}\nSession length: {req.duration_minutes} minutes\n"
            + (f"Course: {course.code} {course.title} (semester {course.semester})\n" if course else "")
            + (f"Faculty notes: {req.notes}\n" if req.notes.strip() else "")
        )
        g = await self.ai.gemini_json(system=prompts.TEACHING_MATERIAL, prompt=f"<<request>>\n{request}<</request>>",
                                      schema=_Material, temperature=0.5, max_tokens=8192, timeout_s=90)
        if g is None or not g.sections:
            raise AIUnavailable("Gemini didn't return usable material. Try again.")
        out = TeachingMaterialOut(
            title=g.title.strip()[:200] or req.topic, overview=g.overview.strip()[:1500],
            learning_outcomes=_items(g.learning_outcomes, 6), sections=_sections(g.sections, 8),
            examples=_sections(g.examples, 3), real_world_examples=_items(g.real_world_examples, 5),
            common_mistakes=_items(g.common_mistakes, 6), discussion_questions=_items(g.discussion_questions, 6),
            viva_questions=[VivaItem(question=v.question.strip()[:400], answer=v.answer.strip()[:800])
                            for v in g.viva_questions if v.question.strip()][:8],
            markdown="", model=self.ai.gemini_model, source="gemini",
        )
        out.markdown = material_markdown(out, req.level)
        return out
