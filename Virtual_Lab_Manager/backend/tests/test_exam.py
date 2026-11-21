"""Exam lockdown: one-tab enforcement, lock on leaving, mentor unlock, live monitor, Safe Exam Browser."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import content as C
from app.config import Settings
from app.db.seed_data import DEMO_PASSWORD, email_for, sid
from app.main import create_app
from tests.conftest import make_repo

BST_ID = sid("practical:bst")  # seeded in strict exam mode
SEB_KEY = "a" * 64


@pytest.fixture(scope="module")
def client(storage):
    settings = Settings(_env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
                        jwt_secret="test-secret-test-secret-test-secret-123", cors_origins="http://localhost:3000")
    with TestClient(create_app(settings, repo=make_repo(storage))) as c:
        yield c


def auth(client, name):
    r = client.post("/api/auth/login", json={"email": email_for(name), "password": DEMO_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def start(client, h, session, practical=BST_ID, extra=None):
    return client.post(f"/api/student/practicals/{practical}/exam/start", headers={**h, **(extra or {})},
                       json={"session_id": session})


def run(client, h, session, practical=BST_ID):
    return client.post(f"/api/student/practicals/{practical}/run", headers={**h, "X-Exam-Session": session},
                       json={"files": {"main.py": C.BST_DEMO_DRAFT}, "mode": "test"})


def monitor_row(client, name, practical=BST_ID):
    rows = client.get(f"/api/faculty/practicals/{practical}/monitor", headers=auth(client, "Meera Kulkarni")).json()["rows"]
    return next(r for r in rows if r["student_name"] == name)


def student_id(name):
    return sid("user:" + email_for(name))


def test_exam_state_on_practical(client):
    p = client.get(f"/api/student/practicals/{BST_ID}", headers=auth(client, "Tara Shetty")).json()
    assert p["lockdown_mode"] == "exam" and p["exam"]["status"] == "not_started"


def test_must_start_before_working(client):
    h = auth(client, "Tara Shetty")
    r = run(client, h, str(uuid.uuid4()))
    assert r.status_code == 409 and "Start the exam" in r.json()["detail"]


def test_single_tab_and_second_tab_locks(client):
    h = auth(client, "Meher Kapoor")
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    first = start(client, h, a).json()
    assert first["status"] == "active" and first["is_current_session"]
    assert run(client, h, a).status_code == 200
    assert run(client, h, b).status_code == 409                      # other tab can't act without claiming
    second = start(client, h, b).json()                              # claiming from a 2nd tab while 1st is live
    assert second["status"] == "locked" and "second tab" in second["lock_reason"]
    locked = run(client, h, a)
    assert locked.status_code == 423 and "Ask your mentor" in locked.json()["detail"]


def test_violation_locks_and_mentor_unlocks(client):
    h = auth(client, "Atharv Gokhale")
    s = str(uuid.uuid4())
    start(client, h, s)
    v = client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h,
                    json={"session_id": s, "type": "focus_lost"}).json()
    assert v["status"] == "locked" and "Left the exam window" in v["lock_reason"]
    assert run(client, h, s).status_code == 423

    row = monitor_row(client, "Atharv Gokhale")
    assert row["status"] == "locked" and row["violations"] == 1
    alerts = client.get("/api/faculty/alerts", headers=auth(client, "Meera Kulkarni")).json()
    assert any(a["student_name"] == "Atharv Gokhale" for a in alerts["locked"])
    assert client.get("/api/faculty/alerts", headers=auth(client, "Rajesh Deshpande")).json()["locked_count"] >= 1

    unlocked = client.post(f"/api/faculty/practicals/{BST_ID}/exam/{student_id('Atharv Gokhale')}/unlock",
                           headers=auth(client, "Meera Kulkarni"))
    assert unlocked.status_code == 200 and unlocked.json()["status"] == "active"
    hb = client.post(f"/api/student/practicals/{BST_ID}/exam/heartbeat", headers=h, json={"session_id": s}).json()
    assert hb["awaiting_resume"] is True
    assert start(client, h, s).json()["is_current_session"] is True  # same tab resumes
    assert run(client, h, s).status_code == 200


def test_interrupted_session_locks(client):
    h = auth(client, "Navya Pillai")
    old = str(uuid.uuid4())
    start(client, h, old)
    repo = client.app.state.repo  # storage-agnostic: go through the repository API on the app's event loop
    attempt = client.portal.call(repo.get_exam_attempt, BST_ID, student_id("Navya Pillai"))
    attempt.last_heartbeat_at = attempt.last_heartbeat_at - timedelta(minutes=5)  # tab was closed long ago
    client.portal.call(repo.save_exam_attempt, attempt)
    st = start(client, h, str(uuid.uuid4())).json()
    assert st["status"] == "locked" and "interrupted" in st["lock_reason"]


def test_page_closed_locks_with_clear_reason(client):
    h = auth(client, "Aditya Kulkarni")
    s = str(uuid.uuid4())
    start(client, h, s)
    v = client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h,
                    json={"session_id": s, "type": "page_closed"}).json()
    assert v["status"] == "locked" and "Left the exam page" in v["lock_reason"] and v["violations"] == 1
    # the reloaded page (new session) sees the lock instead of being treated as a second tab
    again = start(client, h, str(uuid.uuid4())).json()
    assert again["status"] == "locked" and "Left the exam page" in again["lock_reason"] and again["violations"] == 1


def test_only_the_exam_tab_can_lock_or_count(client):
    h = auth(client, "Anika Bhosale")
    s = str(uuid.uuid4())
    start(client, h, s)
    stale = client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h,
                        json={"session_id": str(uuid.uuid4()), "type": "focus_lost"}).json()
    assert stale["status"] == "active" and stale["violations"] == 0
    client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h, json={"session_id": s, "type": "focus_lost"})
    dup = client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h,
                      json={"session_id": s, "type": "fullscreen_exit"}).json()
    assert dup["status"] == "locked" and dup["violations"] == 1 and "Left the exam window" in dup["lock_reason"]


def test_mentor_manual_lock(client):
    h = auth(client, "Shaurya Thakur")
    s = str(uuid.uuid4())
    start(client, h, s)
    r = client.post(f"/api/faculty/practicals/{BST_ID}/exam/{student_id('Shaurya Thakur')}/lock",
                    headers=auth(client, "Meera Kulkarni"), json={"reason": "phone on desk"})
    assert r.json()["status"] == "locked" and "phone on desk" in r.json()["lock_reason"]
    assert run(client, h, s).status_code == 423


def test_submit_ends_exam(client):
    h = auth(client, "Riya Banerjee")
    s = str(uuid.uuid4())
    start(client, h, s)
    sub = client.post(f"/api/student/practicals/{BST_ID}/submit", headers={**h, "X-Exam-Session": s},
                      json={"files": {"main.py": C.BST_SOLUTION}})
    assert sub.status_code == 200
    again = run(client, h, s)
    assert again.status_code == 409 and "already been submitted" in again.json()["detail"]
    assert monitor_row(client, "Riya Banerjee")["status"] == "submitted"


def test_timeline_records_lock_events(client):
    fac = auth(client, "Meera Kulkarni")
    h = auth(client, "Ishita Deshmukh")
    s = str(uuid.uuid4())
    start(client, h, s)
    client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h, json={"session_id": s, "type": "fullscreen_exit"})
    client.post(f"/api/faculty/practicals/{BST_ID}/exam/{student_id('Ishita Deshmukh')}/unlock", headers=fac)
    start(client, h, s)
    sub = client.post(f"/api/student/practicals/{BST_ID}/submit", headers={**h, "X-Exam-Session": s},
                      json={"files": {"main.py": C.BST_SOLUTION}}).json()
    types = [e["type"] for e in client.get(f"/api/faculty/submissions/{sub['id']}/proctor-events", headers=fac).json()]
    assert "exam_locked" in types and "exam_unlocked" in types


def test_monitor_rbac(client):
    assert client.get(f"/api/faculty/practicals/{BST_ID}/monitor", headers=auth(client, "Sanjay Patil")).status_code == 403
    assert client.get(f"/api/faculty/practicals/{BST_ID}/monitor", headers=auth(client, "Tara Shetty")).status_code == 403
    m = client.get(f"/api/faculty/practicals/{BST_ID}/monitor", headers=auth(client, "Meera Kulkarni")).json()
    assert m["lockdown_mode"] == "exam" and len(m["rows"]) == 24 and m["counts"]["locked"] >= 1


def test_client_cannot_forge_server_events(client):
    h = auth(client, "Tara Shetty")
    r = client.post(f"/api/student/practicals/{BST_ID}/proctor/events", headers=h,
                    json={"session_id": str(uuid.uuid4()), "events": [{"type": "exam_unlocked", "at": "2026-11-20T10:00:00Z"}]})
    assert r.status_code == 422


# ---------------------------------------------------------------- Pause button (declared breaks)
def pause(client, h, session, practical=BST_ID):
    return client.post(f"/api/student/practicals/{practical}/exam/pause", headers=h, json={"session_id": session})


def resume(client, h, session, practical=BST_ID):
    return client.post(f"/api/student/practicals/{practical}/exam/resume", headers=h, json={"session_id": session})


def violate(client, h, session, kind="focus_lost"):
    return client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h,
                       json={"session_id": session, "type": kind})


def test_break_pauses_without_locking_and_resumes_in_a_new_tab(client):
    h = auth(client, "Ishaan Chavan")
    tab = str(uuid.uuid4())
    assert start(client, h, tab).json()["status"] == "active"
    p = pause(client, h, tab).json()
    assert p["status"] == "paused" and p["paused_at"] and p["breaks_used"] == 1 and p["max_breaks"] == 2
    assert p["break_limit_s"] == 600 and not p["is_current_session"]
    blocked = run(client, h, tab)
    assert blocked.status_code == 423 and "paused" in blocked.json()["detail"]   # no work during the break
    assert violate(client, h, tab).json()["status"] == "paused"                   # leaving isn't a violation
    row = monitor_row(client, "Ishaan Chavan")
    assert row["status"] == "paused" and row["breaks_used"] == 1 and row["paused_at"]
    new_tab = str(uuid.uuid4())                                                   # closed the tab during the break
    r = resume(client, h, new_tab).json()
    assert r["status"] == "active" and r["is_current_session"] and r["violations"] == 0 and r["paused_at"] is None
    assert run(client, h, new_tab).status_code == 200
    assert run(client, h, tab).status_code == 409                                 # the old tab no longer holds it
    events = client.portal.call(client.app.state.repo.list_proctor_events, BST_ID, student_id("Ishaan Chavan"))
    kinds = [e.event_type for e in events]
    assert "break_start" in kinds and "break_end" in kinds and "exam_locked" not in kinds
    assert monitor_row(client, "Ishaan Chavan")["break_ms"] >= 0


def test_breaks_are_limited(client):
    h = auth(client, "Rohan Jadhav")
    tab = str(uuid.uuid4())
    start(client, h, tab)
    for _ in range(2):
        assert pause(client, h, tab).json()["status"] == "paused"
        assert resume(client, h, tab).json()["status"] == "active"
    third = pause(client, h, tab)
    assert third.status_code == 409 and "all 2 breaks" in third.json()["detail"]
    other = pause(client, h, str(uuid.uuid4()))                                   # only the exam tab can pause
    assert other.status_code == 409


def test_break_over_the_limit_locks(client):
    h = auth(client, "Myra Joshi")
    tab = str(uuid.uuid4())
    start(client, h, tab)
    pause(client, h, tab)
    repo = client.app.state.repo
    a = client.portal.call(repo.get_exam_attempt, BST_ID, student_id("Myra Joshi"))
    a.paused_at = a.paused_at - timedelta(minutes=11)                              # 11 minutes later…
    client.portal.call(repo.save_exam_attempt, a)
    assert monitor_row(client, "Myra Joshi")["status"] == "locked"                # faculty see it at once
    r = resume(client, h, tab).json()
    assert r["status"] == "locked" and "10-minute limit" in r["lock_reason"] and r["violations"] == 1
    fac = auth(client, "Meera Kulkarni")
    assert client.post(f"/api/faculty/practicals/{BST_ID}/exam/{student_id('Myra Joshi')}/unlock",
                       headers=fac).status_code == 200


def test_proctored_lab_breaks_are_summarised(client):
    """Non-exam proctored labs: the client records declared breaks; they are summarised, not counted as leaving."""
    h = auth(client, "Kiara Menon")
    pid = sid("practical:ohms_law")
    sess = str(uuid.uuid4())
    events = [{"type": "session_start", "at": "2026-11-20T10:00:00Z"},
              {"type": "break_start", "at": "2026-11-20T10:05:00Z"},
              {"type": "break_end", "at": "2026-11-20T10:12:00Z", "detail": {"duration_ms": 420000}}]
    r = client.post(f"/api/student/practicals/{pid}/proctor/events", headers=h,
                    json={"session_id": sess, "events": events})
    assert r.status_code == 200, r.text
    summary = r.json()["summary"]
    assert summary["breaks"] == 1 and summary["break_ms"] == 420000 and summary["focus_lost"] == 0


# ---------------------------------------------------------------- Safe Exam Browser
@pytest.fixture(scope="module")
def seb_practical(client):
    fac = auth(client, "Meera Kulkarni")
    body = {"course_id": sid("course:CS201"), "title": "Lab 4 (SEB exam)", "description": "", "lab_type": "coding",
            "starter_files": {"main.py": C.BST_STARTER}, "test_cases": [t.model_dump() for t in C.BST_TESTS],
            "rubric": [r.model_dump() for r in C.BST_RUBRIC], "max_score": 10, "due_at": None, "status": "published",
            "proctored": True, "lockdown_mode": "seb", "seb_config_key": SEB_KEY.upper(),
            "seb_config_url": "https://exams.example.edu/lab4.seb"}
    r = client.post("/api/faculty/practicals", headers=fac, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_seb_settings_validation(client):
    fac = auth(client, "Meera Kulkarni")
    base = {"course_id": sid("course:CS201"), "title": "x lab", "description": "", "lab_type": "coding",
            "starter_files": {"main.py": "x = 1"}, "test_cases": [], "rubric": [{"id": "a", "name": "A", "max_points": 1}],
            "max_score": 10, "due_at": None, "status": "draft", "lockdown_mode": "seb"}
    assert client.post("/api/faculty/practicals", headers=fac, json=base).status_code == 422
    assert client.post("/api/faculty/practicals", headers=fac, json={**base, "seb_config_key": "nothex"}).status_code == 422


def test_seb_key_never_reaches_students(client, seb_practical):
    assert seb_practical["seb_config_key"] == SEB_KEY and seb_practical["seb_launch_url"] == "sebs://exams.example.edu/lab4.seb"
    p = client.get(f"/api/student/practicals/{seb_practical['id']}", headers=auth(client, "Kiara Menon")).json()
    assert p["seb_config_key"] is None and p["exam"]["seb_required"] is True and p["exam"]["seb_verified"] is False


def test_seb_required_and_verified(client, seb_practical):
    pid = seb_practical["id"]
    h = auth(client, "Kiara Menon")
    assert start(client, h, str(uuid.uuid4()), pid).status_code == 403          # plain browser

    page = f"http://localhost:3000/student/labs/{pid}"
    js_hash = hashlib.sha256((page + SEB_KEY).encode()).hexdigest()               # SafeExamBrowser.security.configKey
    bad = {"X-SEB-Page-Url": page, "X-SEB-ConfigKey-Hash": "0" * 64}
    assert start(client, h, str(uuid.uuid4()), pid, bad).status_code == 403
    other_page = {"X-SEB-Page-Url": "http://evil.example/student/labs/" + pid,
                  "X-SEB-ConfigKey-Hash": hashlib.sha256(("http://evil.example/student/labs/" + pid + SEB_KEY).encode()).hexdigest()}
    assert start(client, h, str(uuid.uuid4()), pid, other_page).status_code == 403  # origin not allowed

    s = str(uuid.uuid4())
    seb = {"X-SEB-Page-Url": page + "#editor", "X-SEB-ConfigKey-Hash": js_hash}  # fragment is ignored
    ok = start(client, h, s, pid, seb)
    assert ok.status_code == 200 and ok.json()["status"] == "active" and ok.json()["seb_verified"] is True
    r = client.post(f"/api/student/practicals/{pid}/run", headers={**h, **seb, "X-Exam-Session": s},
                    json={"files": {"main.py": C.BST_DEMO_DRAFT}, "mode": "test"})
    assert r.status_code == 200
    no_seb = client.post(f"/api/student/practicals/{pid}/run", headers={**h, "X-Exam-Session": s},
                         json={"files": {"main.py": C.BST_DEMO_DRAFT}, "mode": "test"})
    assert no_seb.status_code == 403


def test_seb_native_header(client, seb_practical):
    pid = seb_practical["id"]
    url = f"http://testserver/api/student/practicals/{pid}/exam/start"
    native = {"X-SafeExamBrowser-ConfigKeyHash": hashlib.sha256((url + SEB_KEY).encode()).hexdigest()}
    r = start(client, auth(client, "Vihaan Rao"), str(uuid.uuid4()), pid, native)
    assert r.status_code == 200 and r.json()["seb_verified"] is True
