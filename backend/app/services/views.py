"""Map domain records to API response models (batch-loading related rows)."""

from __future__ import annotations

from app.db.base import Repository
from app.models import CourseRecord, PracticalRecord, SubmissionRecord, UserRecord
from app.schemas import CourseOut, PracticalOut, SubmissionOut
from app.services.exam import seb_launch_url


async def courses_out(repo: Repository, courses: list[CourseRecord]) -> list[CourseOut]:
    enroll = await repo.list_enrollments([c.id for c in courses])
    faculty = await repo.get_users([c.faculty_id for c in courses if c.faculty_id])
    return [
        CourseOut(
            id=c.id, code=c.code, title=c.title, semester=c.semester, department_id=c.department_id,
            faculty_id=c.faculty_id,
            faculty_name=faculty[c.faculty_id].full_name if c.faculty_id in faculty else None,
            enrolled=len(enroll.get(c.id, [])),
        )
        for c in courses
    ]


def practical_out(p: PracticalRecord, course: CourseRecord, *, include_hidden: bool) -> PracticalOut:
    tests = p.test_cases if include_hidden else [t for t in p.test_cases if not t.hidden]
    if p.lab_type == "worksheet" and not include_hidden:
        # a worksheet check's code contains the expected answer: students only see what each check is about
        tests = [t.model_copy(update={"code": None}) for t in tests]
    return PracticalOut(
        id=p.id, course_id=p.course_id, course_code=course.code, course_title=course.title, title=p.title,
        description=p.description, lab_type=p.lab_type, language=p.language, starter_files=p.starter_files,
        test_cases=tests, hidden_test_count=sum(1 for t in p.test_cases if t.hidden), rubric=p.rubric,
        max_score=p.max_score, due_at=p.due_at, status=p.status, proctored=p.proctored,
        lockdown_mode=p.lockdown_mode, seb_config_url=p.seb_config_url, seb_launch_url=seb_launch_url(p.seb_config_url),
        seb_config_key=p.seb_config_key if include_hidden else None,  # staff view only
        worksheet=p.worksheet, created_at=p.created_at,
    )


def submission_out(
    s: SubmissionRecord, p: PracticalRecord, course: CourseRecord, student: UserRecord | None, *, include_integrity: bool
) -> SubmissionOut:
    return SubmissionOut(
        id=s.id, practical_id=s.practical_id, practical_title=p.title, course_code=course.code, lab_type=p.lab_type,
        student_id=s.student_id, student_name=student.full_name if student else "Unknown student",
        roll_number=student.roll_number if student else None, files=s.files, status=s.status,
        tests_passed=s.tests_passed, tests_total=s.tests_total, test_results=s.test_results,
        rubric_score=s.rubric_score, max_score=s.max_score, rubric_breakdown=s.rubric_breakdown,
        ai_feedback=s.ai_feedback, grading_model=s.grading_model, faculty_score=s.faculty_score,
        faculty_comment=s.faculty_comment, final_score=s.final_score, submitted_at=s.submitted_at,
        graded_at=s.graded_at, reviewed_at=s.reviewed_at,
        integrity=s.integrity if include_integrity else None,
    )


async def submissions_out(
    repo: Repository,
    subs: list[SubmissionRecord],
    practicals: dict[str, PracticalRecord] | None = None,
    courses: dict[str, CourseRecord] | None = None,
    *,
    include_integrity: bool = False,
) -> list[SubmissionOut]:
    practicals = dict(practicals or {})
    courses = dict(courses or {})
    for s in subs:
        if s.practical_id not in practicals:
            p = await repo.get_practical(s.practical_id)
            if p:
                practicals[p.id] = p
    for p in practicals.values():
        if p.course_id not in courses:
            c = await repo.get_course(p.course_id)
            if c:
                courses[c.id] = c
    students = await repo.get_users([s.student_id for s in subs])
    out = []
    for s in subs:
        p = practicals.get(s.practical_id)
        if p is None or p.course_id not in courses:
            continue
        out.append(submission_out(s, p, courses[p.course_id], students.get(s.student_id),
                                  include_integrity=include_integrity))
    return out
