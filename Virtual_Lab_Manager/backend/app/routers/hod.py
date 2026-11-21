from __future__ import annotations

import csv
import io
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.deps import Svc
from app.models import utcnow
from app.schemas import AskRequest, AskResponse, AssignFacultyRequest, CourseOut
from app.security import HodUser
from app.services import analytics
from app.services.views import courses_out

router = APIRouter(prefix="/api/hod", tags=["hod"])

COMPLIANCE_COLUMNS = [
    "course_code", "course_title", "faculty_name", "practical_title", "due_at", "enrolled", "submitted",
    "completion_rate", "avg_score_pct", "status",
]

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_-]")

# Spreadsheet apps evaluate a cell that starts with one of these as a formula (CSV injection, CWE-1236).
# Titles are typed by faculty (or AI-generated), so text cells are prefixed with ' to keep them literal.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(row: dict) -> dict:
    return {k: f"'{v}" if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES) else v for k, v in row.items()}


@router.get("/overview")
async def overview(user: HodUser, svc: Svc):
    data = await analytics.load_department(svc.repo, user.department_id)
    return analytics.overview(data)


@router.get("/faculty")
async def faculty(user: HodUser, svc: Svc):
    members = await svc.repo.list_users(user.department_id, "faculty")
    courses = await svc.repo.list_courses(department_id=user.department_id)
    return [
        {"id": f.id, "full_name": f.full_name, "email": f.email,
         "courses": [c.code for c in courses if c.faculty_id == f.id]}
        for f in members
    ]


@router.put("/courses/{course_id}/faculty", response_model=CourseOut)
async def assign_faculty(course_id: str, body: AssignFacultyRequest, user: HodUser, svc: Svc):
    course = await svc.repo.get_course(course_id)
    if course is None or course.department_id != user.department_id:
        raise HTTPException(status_code=404, detail="Not found")
    fac = await svc.repo.get_user(body.faculty_id)
    if fac is None or fac.role != "faculty" or fac.department_id != user.department_id:
        raise HTTPException(status_code=422, detail="faculty_id must be a faculty member of your department")
    updated = await svc.repo.set_course_faculty(course.id, fac.id)
    return (await courses_out(svc.repo, [updated]))[0]


@router.get("/compliance-report")
async def compliance_report(user: HodUser, svc: Svc, format: Literal["json", "csv"] = Query("json")):
    data = await analytics.load_department(svc.repo, user.department_id)
    rows = analytics.compliance_rows(data)
    now = utcnow()
    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=COMPLIANCE_COLUMNS)
        writer.writeheader()
        writer.writerows(_csv_safe(r) for r in rows)
        safe_code = _SAFE_FILENAME.sub("_", data.department.code) or "dept"
        filename = f"compliance_{safe_code}_{now:%Y%m%d}.csv"
        return Response(
            content=buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return {"generated_at": now, "department": data.department.name, "rows": rows}


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, user: HodUser, svc: Svc):
    data = await analytics.load_department(svc.repo, user.department_id)
    return await svc.analyst.ask(body.question, analytics.llm_snapshot(data))
