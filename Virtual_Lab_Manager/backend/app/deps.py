"""Service container + resource-level authorization helpers (row-level RBAC)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.ai.analyst import HodAnalyst
from app.ai.briefing import DepartmentBriefingGenerator
from app.ai.difficulties import LearningDifficultyAnalyzer
from app.ai.practical_gen import PracticalGenerator
from app.ai.teaching import TeachingMaterialGenerator
from app.ai.client import AIClient
from app.ai.grader import RubricGrader
from app.ai.integrity import IntegrityAnalyzer
from app.ai.linter import HybridLinter
from app.ai.testgen import TestGenerator
from app.ai.tutor import SocraticTutor
from app.ai.tutor_chat import LabTutor
from app.db.base import Repository
from app.execution.service import ExecutionService
from app.models import CourseRecord, PracticalRecord, SubmissionRecord, UserRecord


@dataclass
class Services:
    repo: Repository
    execution: ExecutionService
    ai: AIClient
    tutor: SocraticTutor
    lab_tutor: LabTutor
    grader: RubricGrader
    linter: HybridLinter
    testgen: TestGenerator
    analyst: HodAnalyst
    integrity: IntegrityAnalyzer
    practical_gen: PracticalGenerator
    teaching: TeachingMaterialGenerator
    difficulties: LearningDifficultyAnalyzer
    briefing: DepartmentBriefingGenerator


def get_services(request: Request) -> Services:
    return request.app.state.services


Svc = Annotated[Services, Depends(get_services)]

_NOT_FOUND = HTTPException(status_code=404, detail="Not found")


async def student_practical(svc: Services, user: UserRecord, practical_id: str) -> tuple[PracticalRecord, CourseRecord]:
    """A student may only access published practicals of courses they're enrolled in."""
    p = await svc.repo.get_practical(practical_id)
    if p is None or p.status != "published":
        raise _NOT_FOUND
    if not await svc.repo.is_enrolled(p.course_id, user.id):
        raise _NOT_FOUND  # don't reveal existence
    course = await svc.repo.get_course(p.course_id)
    assert course is not None
    return p, course


async def staff_course(svc: Services, user: UserRecord, course_id: str) -> CourseRecord:
    """Faculty: only courses they teach. HOD: any course in their department."""
    c = await svc.repo.get_course(course_id)
    if c is None or c.department_id != user.department_id:
        raise _NOT_FOUND
    if user.role == "faculty" and c.faculty_id != user.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this course")
    return c


async def staff_practical(svc: Services, user: UserRecord, practical_id: str) -> tuple[PracticalRecord, CourseRecord]:
    p = await svc.repo.get_practical(practical_id)
    if p is None:
        raise _NOT_FOUND
    return p, await staff_course(svc, user, p.course_id)


async def staff_submission(svc: Services, user: UserRecord, submission_id: str) -> tuple[SubmissionRecord, PracticalRecord, CourseRecord]:
    s = await svc.repo.get_submission(submission_id)
    if s is None:
        raise _NOT_FOUND
    p, c = await staff_practical(svc, user, s.practical_id)
    return s, p, c


async def staff_courses(svc: Services, user: UserRecord) -> list[CourseRecord]:
    if user.role == "hod":
        return await svc.repo.list_courses(department_id=user.department_id)
    return await svc.repo.list_courses(faculty_id=user.id)
