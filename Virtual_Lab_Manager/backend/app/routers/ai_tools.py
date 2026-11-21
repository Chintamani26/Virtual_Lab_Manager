"""AI teaching assistant (faculty) and department intelligence (HOD) endpoints — docs/API.md v1.6.

Everything generated here is a draft or a recommendation: nothing is saved, published or sent automatically.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException

from app.ai.practical_gen import AIUnavailable
from app.deps import Svc, staff_course, staff_courses
from app.models import CourseRecord, UserRecord, utcnow
from app.schemas import (
    DepartmentBriefingOut,
    GeneratedPracticalOut,
    GeneratePracticalRequest,
    LearningDifficultiesOut,
    TeachingMaterialOut,
    TeachingMaterialRequest,
)
from app.security import FacultyUser, HodUser
from app.services import analytics
from app.services.insights import difficulty_evidence, weekly_metrics

faculty_router = APIRouter(prefix="/api/faculty/ai", tags=["faculty-ai"])
hod_router = APIRouter(prefix="/api/hod/ai", tags=["hod-ai"])

GENERATIONS_PER_HOUR = 20  # per user: each one is a long Gemini call (and sandbox runs for practicals)
_generations: dict[str, deque] = defaultdict(deque)


def _limit(user: UserRecord) -> None:
    now = time.monotonic()
    q = _generations[user.id]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= GENERATIONS_PER_HOUR:
        raise HTTPException(status_code=429, detail=f"You've used {GENERATIONS_PER_HOUR} AI generations this hour. "
                                                    "Try again a little later.")
    q.append(now)


async def _course(svc, user: UserRecord, course_id: str | None) -> CourseRecord | None:
    return await staff_course(svc, user, course_id) if course_id else None


@faculty_router.post("/generate-practical", response_model=GeneratedPracticalOut)
async def generate_practical(body: GeneratePracticalRequest, user: FacultyUser, svc: Svc):
    """A complete coding practical from a topic, verified in the sandbox. Returned as a draft for the form."""
    course = await _course(svc, user, body.course_id)
    _limit(user)
    try:
        return await svc.practical_gen.generate(body, course)
    except AIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@faculty_router.post("/teaching-material", response_model=TeachingMaterialOut)
async def teaching_material(body: TeachingMaterialRequest, user: FacultyUser, svc: Svc):
    course = await _course(svc, user, body.course_id)
    _limit(user)
    try:
        return await svc.teaching.generate(body, course)
    except AIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@faculty_router.get("/learning-difficulties", response_model=LearningDifficultiesOut)
async def faculty_difficulties(user: FacultyUser, svc: Svc, refresh: bool = False):
    """Where students struggle in the courses this faculty member teaches (HOD: the whole department)."""
    course_ids = {c.id for c in await staff_courses(svc, user)}
    data = await analytics.load_department(svc.repo, user.department_id)
    threads = await svc.repo.list_tutor_threads([p.id for p in data.practicals if p.course_id in course_ids])
    evidence = difficulty_evidence(data, threads, course_ids)
    return await svc.difficulties.analyze(f"staff:{user.id}", evidence, refresh=refresh)


@hod_router.get("/learning-difficulties", response_model=LearningDifficultiesOut)
async def hod_difficulties(user: HodUser, svc: Svc, refresh: bool = False):
    data = await analytics.load_department(svc.repo, user.department_id)
    threads = await svc.repo.list_tutor_threads([p.id for p in data.practicals])
    return await svc.difficulties.analyze(f"dept:{user.department_id}", difficulty_evidence(data, threads),
                                          refresh=refresh)


@hod_router.post("/briefing", response_model=DepartmentBriefingOut)
async def briefing(user: HodUser, svc: Svc):
    data = await analytics.load_department(svc.repo, user.department_id)
    now = utcnow()
    return await svc.briefing.generate(weekly_metrics(data, now), now)
