"""Proctoring telemetry + academic-integrity (AI-generated / copied code) detection."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import content as C
from app.config import Settings
from app.db.seed_data import DEMO_PASSWORD, email_for, sid
from app.main import create_app
from tests.conftest import make_repo

BST_ID = sid("practical:bst")


@pytest.fixture(scope="module")
def client(storage):
    settings = Settings(_env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
                        jwt_secret="test-secret-test-secret-test-secret-123")
    with TestClient(create_app(settings, repo=make_repo(storage))) as c:
        yield c


def auth(client: TestClient, name: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email_for(name), "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def send(client, headers, session_id, events=(), stats=None, practical=BST_ID):
    return client.post(f"/api/student/practicals/{practical}/proctor/events", headers=headers,
                       json={"session_id": session_id, "events": list(events), "stats": stats})


def stats(typed: int, large: int = 0, large_chars: int = 0, burst: float = 7.0) -> dict:
    return {"typed_chars": typed, "keystrokes": int(typed * 1.1), "active_ms": typed * 250,
            "large_insertions": large, "large_insertion_chars": large_chars, "max_burst_cps": burst}


def submit(client, h, session_id, files, practical=BST_ID):
    """Lab 4 is an exam-lockdown practical: claim the exam with this tab's session, then submit from it."""
    r = client.post(f"/api/student/practicals/{practical}/exam/start", headers=h, json={"session_id": session_id})
    assert r.status_code == 200 and r.json()["status"] == "active", r.text
    r = client.post(f"/api/student/practicals/{practical}/submit", headers={**h, "X-Exam-Session": session_id},
                    json={"files": files})
    assert r.status_code == 200, r.text
    return r.json()


def faculty_view(client, submission_id):
    return client.get(f"/api/faculty/submissions/{submission_id}", headers=auth(client, "Meera Kulkarni")).json()


# ---------------------------------------------------------------- ingestion
def test_practical_is_proctored_with_summary(client):
    p = client.get(f"/api/student/practicals/{BST_ID}", headers=auth(client, "Aarav Sharma")).json()
    assert p["proctored"] is True
    assert p["proctoring_summary"]["sessions"] == 0


def test_event_ingestion_and_summary(client):
    h = auth(client, "Kiara Menon")
    session = str(uuid.uuid4())
    r = send(client, h, session, [
        {"type": "session_start", "at": now()},
        {"type": "paste_blocked", "at": now()},
        {"type": "paste_blocked", "at": now()},
        {"type": "focus_lost", "at": now(), "detail": {"duration_ms": 45000, "reason": "tab_hidden"}},
        {"type": "devtools_blocked", "at": now()},
    ], stats(120))
    assert r.status_code == 200, r.text
    summary = r.json()["summary"]
    assert r.json()["accepted"] == 5
    assert (summary["sessions"], summary["paste_blocked"], summary["focus_lost"], summary["devtools_blocked"]) == (1, 2, 1, 1)
    assert summary["time_away_ms"] == 45000


def test_event_validation(client):
    h = auth(client, "Kiara Menon")
    assert send(client, h, str(uuid.uuid4()), [{"type": "hack", "at": now()}]).status_code == 422
    assert send(client, h, "not-a-uuid").status_code == 422


def test_session_cannot_be_hijacked(client):
    session = str(uuid.uuid4())
    assert send(client, auth(client, "Tara Shetty"), session, [{"type": "session_start", "at": now()}]).status_code == 200
    assert send(client, auth(client, "Meher Kapoor"), session, [{"type": "paste_blocked", "at": now()}]).status_code == 409


# ---------------------------------------------------------------- integrity on submit
def test_honest_submission_is_low_risk_and_hidden_from_student(client):
    h = auth(client, "Aarav Sharma")
    session = str(uuid.uuid4())
    send(client, h, session, [{"type": "session_start", "at": now()}])          # baseline = saved draft
    send(client, h, session, [], stats(typed=95))                               # typed the small fix
    sub = submit(client, h, session, {"main.py": C.BST_SOLUTION})
    assert sub["integrity"] is None                                             # never shown to students
    report = faculty_view(client, sub["id"])["integrity"]
    assert report["risk_level"] == "low", report
    assert report["proctoring"]["sessions"] == 1


def test_ai_generated_code_is_flagged(client):
    h = auth(client, "Ananya Iyer")
    session = str(uuid.uuid4())
    send(client, h, session, [{"type": "session_start", "at": now()},
                              {"type": "paste_blocked", "at": now()},
                              {"type": "large_insertion", "at": now(), "detail": {"chars": 1400}}],
         stats(typed=60, large=1, large_chars=1400, burst=58))
    sub = submit(client, h, session, {"main.py": C.BST_AI_STYLE})
    report = faculty_view(client, sub["id"])["integrity"]
    keys = {s["key"] for s in report["signals"]}
    assert report["risk_level"] == "high"
    assert report["ai_likelihood"] >= 70
    assert {"typed_ratio", "ai_style", "large_insertion", "typing_burst"} <= keys
    assert report["content"]["ai_style_score"] >= 60 and report["content"]["source"] == "fallback"


def test_submission_without_proctored_session_is_flagged(client):
    fac = auth(client, "Meera Kulkarni")
    body = {"course_id": sid("course:CS201"), "title": "BST practice (proctored, no lockdown)", "description": "",
            "lab_type": "coding", "starter_files": {"main.py": C.BST_STARTER},
            "test_cases": [t.model_dump() for t in C.BST_TESTS], "rubric": [r.model_dump() for r in C.BST_RUBRIC],
            "max_score": 10, "due_at": None, "status": "published", "proctored": True, "lockdown_mode": "off"}
    practice = client.post("/api/faculty/practicals", headers=fac, json=body).json()
    h = auth(client, "Kabir Mehta")
    sub = client.post(f"/api/student/practicals/{practice['id']}/submit", headers=h,
                      json={"files": {"main.py": C.BST_SOLUTION}}).json()
    report = faculty_view(client, sub["id"])["integrity"]
    assert "no_session" in {s["key"] for s in report["signals"]}
    assert report["risk_level"] in ("medium", "high")


def test_copied_code_matches_live_classmate_not_seed_data(client):
    src_h, copy_h = auth(client, "Saanvi Reddy"), auth(client, "Arjun Nair")
    for h, typed in ((src_h, 1600), (copy_h, 1500)):
        s = str(uuid.uuid4())
        send(client, h, s, [{"type": "session_start", "at": now()}], stats(typed))
        sub = submit(client, h, s, {"main.py": C.BST_PEER_SOLUTION})
    report = faculty_view(client, sub["id"])["integrity"]
    assert report["similarity"]["max_peer_similarity"] >= 0.95
    assert report["similarity"]["peer_student_name"] == "Saanvi Reddy"  # seeded Riya/Dhruv are excluded
    assert "peer_similarity" in {s["key"] for s in report["signals"]}


# ---------------------------------------------------------------- faculty / HOD views
def test_seeded_case_studies(client):
    fac = auth(client, "Meera Kulkarni")
    subs = client.get(f"/api/faculty/practicals/{BST_ID}/submissions", headers=fac).json()
    by_name = {s["student_name"]: s for s in subs}
    assert by_name["Vihaan Rao"]["integrity"]["risk_level"] == "high"
    assert by_name["Vihaan Rao"]["integrity"]["ai_likelihood"] >= 70
    assert by_name["Dhruv Agarwal"]["integrity"]["similarity"]["peer_student_name"] == "Riya Banerjee"
    timeline = client.get(f"/api/faculty/submissions/{by_name['Vihaan Rao']['id']}/proctor-events", headers=fac).json()
    types = [e["type"] for e in timeline]
    assert "paste_blocked" in types and "large_insertion" in types and "typing_stats" in types


def test_proctor_timeline_rbac(client):
    sub_id = sid("submission:bst:" + sid("user:" + email_for("Vihaan Rao")))
    assert client.get(f"/api/faculty/submissions/{sub_id}/proctor-events",
                      headers=auth(client, "Sanjay Patil")).status_code == 403
    assert client.get(f"/api/faculty/submissions/{sub_id}/proctor-events",
                      headers=auth(client, "Vihaan Rao")).status_code == 403
    assert client.get("/api/student/submissions", headers=auth(client, "Vihaan Rao")).json()[0]["integrity"] is None


def test_hod_integrity_kpi_and_question(client):
    hod = auth(client, "Rajesh Deshpande")
    assert client.get("/api/hod/overview", headers=hod).json()["kpis"]["integrity_flags"] >= 3
    r = client.post("/api/hod/ask", headers=hod, json={"question": "Which submissions were flagged for AI-generated code?"}).json()
    assert "flagged" in r["answer"] and r["table"] is not None


def test_non_proctored_practical(client):
    fac = auth(client, "Meera Kulkarni")
    tpl = client.get("/api/faculty/templates/coding", headers=fac).json()
    body = {"course_id": sid("course:CS201"), "title": "Open-book practice", "description": "", "lab_type": "coding",
            "starter_files": tpl["starter_files"], "test_cases": tpl["test_cases"], "rubric": tpl["rubric"],
            "max_score": 10, "due_at": None, "status": "published", "proctored": False}
    p = client.post("/api/faculty/practicals", headers=fac, json=body).json()
    assert p["proctored"] is False
    h = auth(client, "Aarav Sharma")
    assert client.get(f"/api/student/practicals/{p['id']}", headers=h).json()["proctoring_summary"] is None
    assert send(client, h, str(uuid.uuid4()), practical=p["id"]).status_code == 409


def test_fast_honest_typist_is_not_flagged(client):
    """Regression: auto-indent/autocomplete bursts must not look like cheating."""
    h = auth(client, "Vivaan Gupta")
    session = str(uuid.uuid4())
    send(client, h, session, [{"type": "session_start", "at": now()}], stats(typed=1900, burst=38))
    sub = submit(client, h, session, {"main.py": C.BST_SOLUTION})
    report = faculty_view(client, sub["id"])["integrity"]
    assert report["ai_likelihood"] < 20, report
    assert not {"typing_burst", "keystroke_mismatch", "typed_ratio"} & {s["key"] for s in report["signals"]}
    # (same code as earlier live submissions in this module -> copy detection fires, correctly)
    assert report["similarity"]["max_peer_similarity"] >= 0.95


def test_text_injected_without_keystrokes_is_flagged(client):
    h = auth(client, "Reyansh Pawar")
    session = str(uuid.uuid4())
    injected = {"typed_chars": 1700, "keystrokes": 40, "active_ms": 60000, "large_insertions": 0,
                "large_insertion_chars": 0, "max_burst_cps": 20}
    send(client, h, session, [{"type": "session_start", "at": now()}], injected)
    sub = submit(client, h, session, {"main.py": C.BST_SOLUTION})
    report = faculty_view(client, sub["id"])["integrity"]
    assert "keystroke_mismatch" in {s["key"] for s in report["signals"]}
    assert report["ai_likelihood"] >= 50
