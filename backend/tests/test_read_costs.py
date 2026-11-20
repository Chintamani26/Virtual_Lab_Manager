"""Read-saving paths (Firestore bills every document read) must stay correct:
access checks, and a Live Lab Monitor that keeps idle totals, reads only new runs and caches submissions."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import content as C
from app.config import Settings
from app.db.seed_data import DEMO_PASSWORD, email_for, sid
from app.main import create_app
from app.models import ProctorEventRecord, ProctorSessionRecord, utcnow
from tests.conftest import make_fake_firestore_repo, make_repo

BST_ID = sid("practical:bst")  # strict exam mode
NM_ID = sid("practical:numerical_methods")  # MA201: only the first 12 students are enrolled


@pytest.fixture(scope="module")
def client(storage):
    settings = Settings(_env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
                        jwt_secret="test-secret-test-secret-test-secret-123", cors_origins="http://localhost:3000")
    with TestClient(create_app(settings, repo=make_repo(storage))) as c:
        yield c


def auth(client, name):
    r = client.post("/api/auth/login", json={"email": email_for(name), "password": DEMO_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def monitor_row(client, name):
    r = client.get(f"/api/faculty/practicals/{BST_ID}/monitor", headers=auth(client, "Meera Kulkarni"))
    assert r.status_code == 200
    return next(row for row in r.json()["rows"] if row["student_name"] == name)


def test_enrolment_check(client):
    assert client.get(f"/api/student/practicals/{NM_ID}", headers=auth(client, "Diya Patel")).status_code == 200
    # repeated: the second answer may come from the cache and must not change
    for _ in range(2):
        assert client.get(f"/api/student/practicals/{NM_ID}", headers=auth(client, "Avni Saxena")).status_code == 404


def test_monitor_follows_new_events_runs_and_submissions(client):
    name = "Navya Pillai"
    h = auth(client, name)
    s = str(uuid.uuid4())
    assert client.post(f"/api/student/practicals/{BST_ID}/exam/start", headers=h,
                       json={"session_id": s}).json()["status"] == "active"
    before = monitor_row(client, name)  # warms every monitor cache (seeded runs / events may already exist)

    now = utcnow().isoformat()
    ev = client.post(f"/api/student/practicals/{BST_ID}/proctor/events", headers=h, json={
        "session_id": s,
        "events": [{"type": "paste_blocked", "at": now},
                   {"type": "focus_lost", "at": now, "detail": {"duration_ms": 1500, "reason": "tab_hidden"}}],
    })
    assert ev.status_code == 200
    run = client.post(f"/api/student/practicals/{BST_ID}/run", headers={**h, "X-Exam-Session": s},
                      json={"files": {"main.py": C.BST_DEMO_DRAFT}, "mode": "test"})
    assert run.status_code == 200

    row = monitor_row(client, name)
    assert row["paste_blocked"] == before["paste_blocked"] + 1
    assert row["focus_lost"] == before["focus_lost"] + 1
    assert row["time_away_ms"] == before["time_away_ms"] + 1500
    assert (row["tests_passed"], row["tests_total"]) == (run.json()["tests_passed"], run.json()["tests_total"])
    assert run.json()["tests_passed"] != before["tests_passed"]  # the new run, not the seeded one

    sub = client.post(f"/api/student/practicals/{BST_ID}/submit", headers={**h, "X-Exam-Session": s},
                      json={"files": {"main.py": C.BST_SOLUTION}})
    assert sub.status_code == 200
    row = monitor_row(client, name)
    assert row["status"] == "submitted" and row["submission_id"] == sub.json()["id"]


def test_firestore_monitor_rereads_only_active_sessions():
    repo = make_fake_firestore_repo()
    db = repo.client
    old = utcnow() - timedelta(hours=1)
    idle = ProctorSessionRecord(id="s-idle", practical_id=BST_ID, student_id="u1", started_at=old, last_seen_at=old)
    live = ProctorSessionRecord(id="s-live", practical_id=BST_ID, student_id="u2", started_at=old, last_seen_at=utcnow())
    asyncio.run(repo.create_proctor_events([
        ProctorEventRecord(practical_id=BST_ID, student_id="u1", session_id="s-idle", event_type="paste_blocked"),
        ProctorEventRecord(practical_id=BST_ID, student_id="u2", session_id="s-live", event_type="focus_lost",
                           detail={"duration_ms": 900}),
    ]))

    first = asyncio.run(repo.practical_proctor_tallies(BST_ID, [idle, live]))
    assert first["u1"] == {"paste_blocked": 1} and first["u2"] == {"focus_lost": 1, "time_away_ms": 900}
    reads = db.reads["proctoring_events"]
    assert asyncio.run(repo.practical_proctor_tallies(BST_ID, [idle])) == {"u1": {"paste_blocked": 1}}
    assert db.reads["proctoring_events"] == reads  # idle session: totals kept, nothing queried
    asyncio.run(repo.practical_proctor_tallies(BST_ID, [idle, live]))
    assert db.reads["proctoring_events"] == reads + 1  # active session: re-read every poll

    # an idle session that becomes active again (new last_seen_at) is re-read
    back = idle.model_copy(update={"last_seen_at": utcnow()})
    asyncio.run(repo.create_proctor_events([
        ProctorEventRecord(practical_id=BST_ID, student_id="u1", session_id="s-idle", event_type="paste_blocked"),
    ]))
    assert asyncio.run(repo.practical_proctor_tallies(BST_ID, [back]))["u1"] == {"paste_blocked": 2}
