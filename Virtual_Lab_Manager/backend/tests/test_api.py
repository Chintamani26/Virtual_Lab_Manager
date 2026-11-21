"""End-to-end API tests against each storage backend (tests/conftest.py) + local runner (AI disabled => deterministic fallbacks)."""

from __future__ import annotations

import json
import random
import uuid

import pytest
from fastapi.testclient import TestClient

from app import content as C
from app import worksheet_labs as W
from app.ai.tutor import _scrub
from app.config import Settings
from app.db.seed_data import DEMO_PASSWORD, email_for, sid
from app.main import create_app
from tests.conftest import make_repo

BST_ID = sid("practical:bst")
NM_ID = sid("practical:numerical_methods")
OHM_ID = sid("practical:ohms_law")
PENDULUM_ID = sid("practical:pendulum")
GRAPH_ID = sid("practical:graph")
CS305_ID = sid("course:CS305")


@pytest.fixture(scope="module")
def client(storage):
    settings = Settings(
        _env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
        jwt_secret="test-secret-test-secret-test-secret-123",
    )
    with TestClient(create_app(settings, repo=make_repo(storage))) as c:
        yield c


def login(client: TestClient, name: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email_for(name), "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


_EXAM_SESSIONS: dict[tuple[int, str], str] = {}


def exam_headers(client: TestClient, name: str, practical: str = BST_ID) -> dict:
    """Lab 4 runs in exam lockdown mode: claim it once per student (per app/storage) and send the session header."""
    h = login(client, name)
    key = (id(client.app), name)
    if key not in _EXAM_SESSIONS:
        sid_ = str(uuid.uuid4())
        r = client.post(f"/api/student/practicals/{practical}/exam/start", headers=h, json={"session_id": sid_})
        assert r.status_code == 200 and r.json()["status"] == "active", r.text
        _EXAM_SESSIONS[key] = sid_
    return {**h, "X-Exam-Session": _EXAM_SESSIONS[key]}


@pytest.fixture(scope="module")
def engine_labs(client):
    """The circuit and notebook engines aren't used by the seeded labs any more: publish one lab of each."""
    def make(faculty: str, course: str, title: str, lab_type: str, files: dict, tests: list, rubric: list) -> str:
        h = login(client, faculty)
        body = {"course_id": sid(f"course:{course}"), "title": title, "description": "", "lab_type": lab_type,
                "starter_files": files, "test_cases": [t.model_dump() for t in tests],
                "rubric": [r.model_dump() for r in rubric], "max_score": 10, "due_at": None, "status": "draft"}
        r = client.post("/api/faculty/practicals", headers=h, json=body)
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        assert client.post(f"/api/faculty/practicals/{pid}/publish", headers=h).status_code == 200
        return pid

    return {
        "circuit": make("Sanjay Patil", "EC210", "Full adder (engine test)", "circuit",  # EE210 keeps the EC210 id
                        {"circuit.sim": C.FULL_ADDER_STARTER}, C.FULL_ADDER_TESTS, C.CIRCUIT_RUBRIC),
        "notebook": make("Neha Joshi", "MA201", "EDA (engine test)", "notebook",
                         {"data.ipynb": C.EDA_STARTER}, C.EDA_TESTS, C.EDA_RUBRIC),
    }


@pytest.fixture(scope="module")
def student(client):
    return login(client, "Aarav Sharma")


@pytest.fixture(scope="module")
def faculty(client):
    return login(client, "Meera Kulkarni")


@pytest.fixture(scope="module")
def hod(client):
    return login(client, "Rajesh Deshpande")


# ---------------------------------------------------------------- auth & RBAC
def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["storage"] == client.app.state.repo.name
    assert body["storage"] in ("memory", "firestore") and body["execution_engine"] == "local-python"
    assert body["auth_provider"] == "local"


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"email": email_for("Aarav Sharma"), "password": "nope"})
    assert r.status_code == 401


def test_demo_accounts(client):
    roles = {a["role"] for a in client.get("/api/auth/demo-accounts").json()}
    assert roles == {"student", "faculty", "hod"}


def test_me(client, student):
    me = client.get("/api/auth/me", headers=student).json()
    assert me["role"] == "student" and me["roll_number"] == "CE23001"


@pytest.mark.parametrize("path", ["/api/student/dashboard", "/api/faculty/dashboard", "/api/hod/overview"])
def test_requires_auth(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_role_isolation(client, student, faculty):
    assert client.get("/api/faculty/dashboard", headers=student).status_code == 403
    assert client.get("/api/hod/overview", headers=student).status_code == 403
    assert client.get("/api/hod/overview", headers=faculty).status_code == 403
    assert client.get("/api/student/dashboard", headers=faculty).status_code == 403


def test_student_cannot_see_draft_or_unenrolled_practicals(client, student):
    assert client.get(f"/api/student/practicals/{GRAPH_ID}", headers=student).status_code == 404
    other = login(client, "Avni Saxena")  # not enrolled in MA201
    assert client.get(f"/api/student/practicals/{NM_ID}", headers=other).status_code == 404


def test_faculty_cannot_touch_other_courses(client):
    sanjay = login(client, "Sanjay Patil")
    assert client.get(f"/api/faculty/practicals/{BST_ID}", headers=sanjay).status_code == 403


def test_hidden_tests_not_exposed_to_students(client, student):
    p = client.get(f"/api/student/practicals/{BST_ID}", headers=student).json()
    assert all(not t["hidden"] for t in p["test_cases"])
    assert p["hidden_test_count"] == 2
    assert p["draft_files"]["main.py"] == C.BST_DEMO_DRAFT


# ---------------------------------------------------------------- hero demo flow
def test_demo_flow_bst(client, student, faculty, hod):
    dash = client.get("/api/student/dashboard", headers=student).json()
    bst = next(p for p in dash["practicals"] if p["id"] == BST_ID)
    assert bst["progress"] == "in_progress"

    student = exam_headers(client, "Aarav Sharma")
    # 1) run tests on the saved draft -> 4 of 5, test_duplicate_keys fails
    run = client.post(f"/api/student/practicals/{BST_ID}/run", headers=student,
                      json={"files": {"main.py": C.BST_DEMO_DRAFT}, "mode": "test"}).json()
    assert run["summary"] == "4 of 5 Tests Passed"
    assert [t["name"] for t in run["tests"] if not t["passed"]] == ["test_duplicate_keys"]
    assert run["execution_id"]

    # 2) progressive Socratic hints focus on the failing test
    h1 = client.post(f"/api/student/practicals/{BST_ID}/hint", headers=student, json={}).json()
    h2 = client.post(f"/api/student/practicals/{BST_ID}/hint", headers=student,
                     json={"question": "why does size grow?"}).json()
    assert h1["focus_test"] == h2["focus_test"] == "test_duplicate_keys"
    assert (h1["hint_level"], h2["hint_level"]) == (1, 2)
    assert "elif" not in h1["hint"] and "return" not in h1["hint"]

    # 3) fix + submit -> hidden tests run, rubric score synced
    sub = client.post(f"/api/student/practicals/{BST_ID}/submit", headers=student,
                      json={"files": {"main.py": C.BST_SOLUTION}}).json()
    assert sub["tests_passed"] == sub["tests_total"] == 7
    assert any(t["hidden"] for t in sub["test_results"])
    assert 7 <= sub["rubric_score"] <= 10
    assert {b["criterion_id"] for b in sub["rubric_breakdown"]} == {"correctness", "edge_cases", "code_quality", "efficiency"}

    # 4) faculty sees it and can override
    fdash = client.get("/api/faculty/dashboard", headers=faculty).json()
    assert any(s["id"] == sub["id"] for s in fdash["recent_submissions"])
    rev = client.post(f"/api/faculty/submissions/{sub['id']}/review", headers=faculty,
                      json={"faculty_score": 9, "faculty_comment": "Great fix"}).json()
    assert rev["status"] == "reviewed" and rev["final_score"] == 9

    # 5) HOD overview reflects bottleneck + hints
    ov = client.get("/api/hod/overview", headers=hod).json()
    assert ov["bottlenecks"][0]["test_name"] == "test_duplicate_keys"
    assert ov["kpis"]["ai_hints_served"] > 0 and len(ov["activity"]) == 14


def test_run_mode_and_syntax_error(client):
    student = exam_headers(client, "Diya Patel")
    r = client.post(f"/api/student/practicals/{BST_ID}/run", headers=student,
                    json={"files": {"main.py": C.BST_DEMO_DRAFT}, "mode": "run"}).json()
    assert r["status"] == "ok" and "Inorder" in r["stdout"]
    bad = client.post(f"/api/student/practicals/{BST_ID}/run", headers=student,
                      json={"files": {"main.py": "def broken(:\n  pass"}, "mode": "test"}).json()
    assert bad["status"] == "compile_error" and bad["tests_passed"] == 0


def test_missing_file_is_422(client):
    student = exam_headers(client, "Diya Patel")
    r = client.post(f"/api/student/practicals/{BST_ID}/run", headers=student, json={"files": {"x.py": ""}, "mode": "test"})
    assert r.status_code == 422


def test_circuit_lab(client, student, engine_labs):
    r = client.post(f"/api/student/practicals/{engine_labs['circuit']}/run", headers=student,
                    json={"files": {"circuit.sim": C.FULL_ADDER_STARTER}, "mode": "test"}).json()
    assert r["engine"] == "circuit-sim" and len(r["truth_table"]) == 8 and r["tests_passed"] < r["tests_total"]
    ok = client.post(f"/api/student/practicals/{engine_labs['circuit']}/run", headers=student,
                     json={"files": {"circuit.sim": C.FULL_ADDER_SOLUTION}, "mode": "test"}).json()
    assert ok["tests_passed"] == ok["tests_total"] == 6  # visible only


def test_notebook_lab(client, student, engine_labs):
    r = client.post(f"/api/student/practicals/{engine_labs['notebook']}/run", headers=student,
                    json={"files": {"data.ipynb": C.EDA_SOLUTION}, "mode": "test"}).json()
    assert r["tests_passed"] == r["tests_total"] == 4
    assert r["cell_outputs"] and r["cell_outputs"][0]["index"] == 1


def test_student_practical_reports_submission_allowance(client, student):
    p = client.get(f"/api/student/practicals/{OHM_ID}", headers=student).json()
    assert p["submission_limit"] == 10 and p["submissions_used"] == 0


WORKSHEETS = [
    (NM_ID, W.NM_TESTS, lambda: W.nm_answers()),
    (PENDULUM_ID, W.PENDULUM_TESTS, lambda: W.pendulum_answers(random.Random(7))),
    (OHM_ID, W.OHM_TESTS, lambda: W.ohm_answers(random.Random(7))),
]


@pytest.mark.parametrize("pid,tests,answers", WORKSHEETS, ids=["maths", "pendulum", "ohm"])
def test_worksheet_checks(client, student, pid, tests, answers):
    url = f"/api/student/practicals/{pid}/run"
    visible = sum(1 for t in tests if not t.hidden)
    ok = client.post(url, headers=student, json={"files": {"answers.json": json.dumps(answers())}, "mode": "test"}).json()
    assert ok["lab_type"] == "worksheet" and ok["tests_passed"] == ok["tests_total"] == visible, ok
    empty = client.post(url, headers=student, json={"files": {"answers.json": W.EMPTY_ANSWERS}, "mode": "test"}).json()
    assert empty["tests_passed"] == 0 and all(t["message"] for t in empty["tests"])


def test_worksheet_hidden_checks_pass_for_reference_answers():
    for _pid, tests, answers in WORKSHEETS:
        assert all(r.passed for r in W.evaluate(tests, answers())), [r for r in W.evaluate(tests, answers()) if not r.passed]


def test_worksheet_student_view_hides_check_code(client, student, faculty):
    p = client.get(f"/api/student/practicals/{NM_ID}", headers=student).json()
    assert p["lab_type"] == "worksheet" and p["worksheet"]["sections"][0]["steps"][0]["test"] == "test_nr_f_x0"
    assert p["test_cases"] and all(t["code"] is None for t in p["test_cases"])  # the code holds the expected value
    staff = client.get(f"/api/faculty/practicals/{NM_ID}", headers=login(client, "Neha Joshi")).json()
    assert all(t["code"] for t in staff["test_cases"])


def test_worksheet_rejects_malformed_answers(client, student):
    url = f"/api/student/practicals/{NM_ID}/run"
    for bad in ("not json", json.dumps([1, 2]), json.dumps({"steps": {"a": "x" * 500}})):
        assert client.post(url, headers=student, json={"files": {"answers.json": bad}, "mode": "test"}).status_code == 422


def test_worksheet_mistake_gets_targeted_feedback(client, student):
    answers = W.ohm_answers(random.Random(3), {"test_r_column"})
    r = client.post(f"/api/student/practicals/{OHM_ID}/run", headers=student,
                    json={"files": {"answers.json": json.dumps(answers)}, "mode": "test"}).json()
    msg = next(t["message"] for t in r["tests"] if t["name"] == "test_r_column")
    assert "amperes" in msg and "220" not in msg


def test_seeded_worksheet_submission_rechecks(client, student):
    sub = client.get(f"/api/student/practicals/{PENDULUM_ID}", headers=student).json()["latest_submission"]
    assert sub and sub["tests_passed"] == sub["tests_total"]
    r = client.post(f"/api/student/practicals/{PENDULUM_ID}/run", headers=student,
                    json={"files": sub["files"], "mode": "test"}).json()
    assert r["tests_passed"] == r["tests_total"]


def test_worksheet_submit_and_hint(client):
    diya = login(client, "Diya Patel")
    wrong = W.nm_answers({"test_nr_x1"})
    client.post(f"/api/student/practicals/{NM_ID}/run", headers=diya,
                json={"files": {"answers.json": json.dumps(wrong)}, "mode": "test"})
    hint = client.post(f"/api/student/practicals/{NM_ID}/hint", headers=diya, json={}).json()
    assert hint["focus_test"] == "test_nr_x1" and "2.1" not in hint["hint"]
    sub = client.post(f"/api/student/practicals/{NM_ID}/submit", headers=diya,
                      json={"files": {"answers.json": json.dumps(W.nm_answers())}})
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["tests_passed"] == body["tests_total"] == len(W.NM_TESTS) and body["rubric_score"] >= 9


def test_student_sees_one_course_per_discipline(client, student):
    d = client.get("/api/student/dashboard", headers=student).json()
    assert [(c["code"], c["title"]) for c in d["courses"]] == [
        ("CS201", "Data Structures Lab"), ("EE210", "Electrical Lab"),
        ("MA201", "Applied Mathematics Lab"), ("PH101", "Physics Lab"),
    ]
    assert sid("course:EC210") in {c["id"] for c in d["courses"]}  # renamed course keeps its id (no stale Firestore copy)
    done = {p["title"]: p for p in d["practicals"] if p["progress"] in ("graded", "submitted")}
    assert {"Lab 3: Singly Linked Lists", "Lab 1: Simple Pendulum — Measuring g"} <= set(done)
    assert all(p["feedback"] and p["tests_total"] and p["submitted_at"] for p in done.values())


def test_lint(client, student, engine_labs):
    diya = exam_headers(client, "Diya Patel")
    r = client.post(f"/api/student/practicals/{BST_ID}/lint", headers=diya,
                    json={"files": {"main.py": "x = (1,\n"}, "filename": "main.py"}).json()
    assert r["diagnostics"][0]["severity"] == "error" and r["diagnostics"][0]["source"] == "syntax"
    c = client.post(f"/api/student/practicals/{engine_labs['circuit']}/lint", headers=student,
                    json={"files": {"circuit.sim": "INPUT A\nOUTPUT Y\nY = FOO(A, A)"}, "filename": "circuit.sim"}).json()
    assert c["diagnostics"][0]["line"] == 3


# ---------------------------------------------------------------- faculty authoring
def test_faculty_create_validate_publish(client, faculty):
    tpl = client.get("/api/faculty/templates/coding", headers=faculty).json()
    body = {
        "course_id": sid("course:CS201"), "title": "Lab 6: Stacks", "description": "Implement push/pop.",
        "lab_type": "coding", "starter_files": {"main.py": "def solve(values):\n    return sorted(values)\n"},
        "test_cases": tpl["test_cases"], "rubric": tpl["rubric"], "max_score": 10, "due_at": None, "status": "draft",
    }
    created = client.post("/api/faculty/practicals", headers=faculty, json=body)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    val = client.post(f"/api/faculty/practicals/{pid}/validate", headers=faculty, json={"files": body["starter_files"]}).json()
    assert val["tests_total"] == 2
    pub = client.post(f"/api/faculty/practicals/{pid}/publish", headers=faculty).json()
    assert pub["status"] == "published"
    gen = client.post("/api/faculty/ai/generate-tests", headers=faculty,
                      json={"title": "x", "description": "y", "lab_type": "circuit"}).json()
    assert gen["source"] == "fallback" and gen["test_cases"]


def test_faculty_rejects_bad_practical(client, faculty):
    body = {
        "course_id": sid("course:CS201"), "title": "Bad lab", "description": "", "lab_type": "notebook",
        "starter_files": {"data.ipynb": "not json"}, "test_cases": [], "rubric": [{"id": "a", "name": "A", "max_points": 1}],
        "max_score": 10, "due_at": None, "status": "draft",
    }
    assert client.post("/api/faculty/practicals", headers=faculty, json=body).status_code == 422


# ---------------------------------------------------------------- HOD
def test_hod_assign_and_reports(client, hod):
    fac = client.get("/api/hod/faculty", headers=hod).json()
    amit = next(f for f in fac if f["full_name"] == "Amit Verma")
    c = client.put(f"/api/hod/courses/{CS305_ID}/faculty", headers=hod, json={"faculty_id": amit["id"]}).json()
    assert c["faculty_name"] == "Amit Verma"
    student_id = sid("user:" + email_for("Aarav Sharma"))
    assert client.put(f"/api/hod/courses/{CS305_ID}/faculty", headers=hod, json={"faculty_id": student_id}).status_code == 422

    rep = client.get("/api/hod/compliance-report", headers=hod).json()
    assert rep["rows"] and {"compliant", "at_risk", "non_compliant"} >= {r["status"] for r in rep["rows"]}
    csv_resp = client.get("/api/hod/compliance-report?format=csv", headers=hod)
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert csv_resp.text.splitlines()[0].startswith("course_code,course_title")


@pytest.mark.parametrize("question,expect", [
    ("What is the most common failing test?", "test_duplicate_keys"),
    ("Which students are at risk in CS201?", "at risk"),
    ("Which lab has the lowest completion rate?", "Lowest completion"),
])
def test_hod_ask_fallback(client, hod, question, expect):
    r = client.post("/api/hod/ask", headers=hod, json={"question": question}).json()
    assert r["source"] == "fallback" and expect in r["answer"]


# ---------------------------------------------------------------- unit
def test_scrub_removes_solution_code():
    text = "Try this:\n```python\ndef insert(self, key):\n    if key == node.key:\n        return\n```\nGood luck"
    out = _scrub(text)
    assert "def insert" not in out and "code removed" in out
    assert _scrub("Look at `key < node.key`") == "Look at `key < node.key`"
