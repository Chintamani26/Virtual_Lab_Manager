"""Firestore-specific behaviour of FirestoreRepository (on the in-process fake): seed shape, the browser-readable
exam_live mirror, heartbeat throttling, staff fan-out, Firestore limits."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import content as C
from app.config import Settings
from app.db import firestore as F
from app.db.seed_data import DEMO_PASSWORD, build_seed, email_for, sid
from app.main import create_app
from app.models import ExecutionLogRecord, utcnow
from tests.conftest import make_fake_firestore_repo

BST_ID = sid("practical:bst")
CS201 = sid("course:CS201")


def uid(name: str) -> str:
    return sid("user:" + email_for(name))


@pytest.fixture(scope="module")
def ctx():
    repo = make_fake_firestore_repo()
    settings = Settings(_env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
                        jwt_secret="test-secret-test-secret-test-secret-123")
    with TestClient(create_app(settings, repo=repo)) as c:
        yield c, repo, repo.client


def auth(client, name):
    r = client.post("/api/auth/login", json={"email": email_for(name), "password": DEMO_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def start(client, h, session):
    r = client.post(f"/api/student/practicals/{BST_ID}/exam/start", headers=h, json={"session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- seed
def test_seed_documents_shape():
    seed = build_seed()
    docs = F.seed_documents(seed, include_password_hash=False)
    by = {}
    for col, doc_id, data in docs:
        by.setdefault(col, {})[doc_id] = data
    assert len(by[F.USERS]) == len(seed.users) and len(by[F.SUBMISSIONS]) == len(seed.submissions)
    assert len(by[F.ENROLLMENTS]) == len(seed.enrollments) and len(by[F.EVENTS]) == len(seed.proctor_events)
    assert all(d["password_hash"] == "" for d in by[F.USERS].values())          # Firebase Auth holds credentials
    aarav = by[F.USERS][uid("Aarav Sharma")]
    assert aarav["email_lower"] == "aarav.sharma@demo.edu"
    enr = next(iter(by[F.ENROLLMENTS]))
    assert enr.count("__") == 1                                                  # {course_id}__{student_id}
    assert all(p["department_id"] for p in by[F.PRACTICALS].values())
    dept = next(iter(by[F.DEPARTMENTS].values()))
    assert dept["hod_ids"] == [uid("Rajesh Deshpande")]
    assert all("expire_at" in d for d in by[F.EXECUTIONS].values())


def test_seed_is_idempotent_and_never_deletes():
    from tests.fake_firestore import FakeFirestore

    fake = FakeFirestore()
    docs = F.seed_documents(build_seed(), include_password_hash=False)
    asyncio.run(F.write_documents(fake, docs))
    asyncio.run(F.write_documents(fake, docs))
    assert len(fake.docs(F.USERS)) == len({d for c, d, _ in docs if c == F.USERS})


# ---------------------------------------------------------------- exam_live mirror
def test_exam_live_mirror_has_display_fields_only(ctx):
    client, repo, fake = ctx
    h, s = auth(client, "Tara Shetty"), str(uuid.uuid4())
    start(client, h, s)
    key = f"{BST_ID}__{uid('Tara Shetty')}"
    live = fake.doc(F.LIVE, key)
    assert live["status"] == "active" and live["student_name"] == "Tara Shetty" and live["course_id"] == CS201
    assert uid("Meera Kulkarni") in live["staff_ids"] and uid("Rajesh Deshpande") in live["staff_ids"]
    assert "active_session_id" not in live and "last_session_id" not in live   # the one-tab secret stays server-side
    assert fake.doc(F.ATTEMPTS, key)["active_session_id"] == s

    client.post(f"/api/student/practicals/{BST_ID}/exam/violation", headers=h, json={"session_id": s, "type": "focus_lost"})
    live = fake.doc(F.LIVE, key)
    assert live["status"] == "locked" and "Left the exam window" in live["lock_reason"] and live["violations"] == 1


def test_heartbeats_are_throttled_and_skip_the_mirror(ctx):
    client, repo, fake = ctx
    h, s = auth(client, "Meher Kapoor"), str(uuid.uuid4())
    start(client, h, s)
    attempts, live = fake.writes[F.ATTEMPTS], fake.writes[F.LIVE]
    for _ in range(5):
        r = client.post(f"/api/student/practicals/{BST_ID}/exam/heartbeat", headers=h, json={"session_id": s})
        assert r.status_code == 200 and r.json()["is_current_session"]
    assert fake.writes[F.ATTEMPTS] == attempts and fake.writes[F.LIVE] == live
    # a stale stored heartbeat is persisted again
    key = f"{BST_ID}__{uid('Meher Kapoor')}"
    repo._persisted[key]["last_heartbeat_at"] -= timedelta(seconds=20)
    client.post(f"/api/student/practicals/{BST_ID}/exam/heartbeat", headers=h, json={"session_id": s})
    assert fake.writes[F.ATTEMPTS] == attempts + 1 and fake.writes[F.LIVE] == live


def test_reassigning_faculty_updates_live_staff(ctx):
    client, repo, fake = ctx
    start(client, auth(client, "Kiara Menon"), str(uuid.uuid4()))
    key = f"{BST_ID}__{uid('Kiara Menon')}"
    client.portal.call(repo.set_course_faculty, CS201, uid("Sanjay Patil"))
    assert uid("Sanjay Patil") in fake.doc(F.LIVE, key)["staff_ids"]
    client.portal.call(repo.set_course_faculty, CS201, uid("Meera Kulkarni"))
    staff = fake.doc(F.LIVE, key)["staff_ids"]
    assert uid("Meera Kulkarni") in staff and uid("Sanjay Patil") not in staff


# ---------------------------------------------------------------- Firestore limits
def test_in_filters_are_chunked():
    repo = make_fake_firestore_repo()  # the fake raises on > 30 values per `in`
    ids = [sid(f"course:none{i}") for i in range(65)] + [CS201]
    out = asyncio.run(repo.list_enrollments(ids))
    assert len(out[CS201]) > 0 and len(out) == 66


def test_execution_output_is_capped():
    repo = make_fake_firestore_repo()
    rec = ExecutionLogRecord(practical_id=BST_ID, student_id=uid("Aarav Sharma"), lab_type="coding", mode="run",
                             engine="local", status="ok", files={"main.py": "x"}, stdout="y" * 200_000,
                             created_at=utcnow())
    asyncio.run(repo.create_execution_log(rec))
    stored = repo.client.doc(F.EXECUTIONS, rec.id)
    assert len(stored["stdout"]) < F.MAX_OUTPUT_CHARS + 100 and "truncated" in stored["stdout"]


def test_reserved_file_names_are_rejected(ctx):
    client, _, _ = ctx
    h = auth(client, "Diya Patel")
    s = str(uuid.uuid4())
    start(client, h, s)
    r = client.put(f"/api/student/practicals/{BST_ID}/draft", headers={**h, "X-Exam-Session": s},
                   json={"files": {"__name__": C.BST_STARTER}})
    assert r.status_code == 422


def test_no_writes_on_startup():
    repo = make_fake_firestore_repo()
    before = sum(repo.client.writes.values())
    settings = Settings(_env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
                        jwt_secret="test-secret-test-secret-test-secret-123")
    with TestClient(create_app(settings, repo=repo)) as c:
        assert c.get("/api/health").json()["storage"] == "firestore"
    assert sum(repo.client.writes.values()) == before


def test_prune_stale_seed_removes_only_leftovers():
    """scripts/prune_stale_seed: retired courses/labs and stale redesigned-lab docs go; seeded and live work stay."""
    from scripts.prune_stale_seed import delete, find_stale
    from tests.fake_firestore import FakeFirestore

    fake = FakeFirestore()
    asyncio.run(F.write_documents(fake, F.seed_documents(build_seed(), include_password_hash=False)))
    aarav = uid("Aarav Sharma")
    planted = [
        (F.COURSES, sid("course:DS301"), {"id": sid("course:DS301"), "code": "DS301"}),
        (F.ENROLLMENTS, F.pair_id(sid("course:CS305"), aarav), {"course_id": sid("course:CS305"), "student_id": aarav}),
        (F.PRACTICALS, sid("practical:half_adder"), {"id": sid("practical:half_adder"), "title": "Lab 2: Half Adder"}),
        (F.SUBMISSIONS, "old-full-adder-sub", {"practical_id": sid("practical:full_adder"), "student_id": aarav}),
        (F.HINTS, "old-eda-hint", {"practical_id": sid("practical:eda"), "student_id": aarav}),
        (F.EXECUTIONS, "old-pendulum-notebook-run", {"practical_id": sid("practical:pendulum"), "student_id": aarav}),
    ]
    live = (F.SUBMISSIONS, "live-bst-sub", {"practical_id": BST_ID, "student_id": aarav})

    async def plant():
        batch = fake.batch()
        for col, doc_id, data in planted + [live]:
            batch.set(fake.collection(col).document(doc_id), data)
        await batch.commit()

    asyncio.run(plant())
    stale = asyncio.run(find_stale(fake))
    assert sorted(stale) == sorted((c, i) for c, i, _ in planted)
    asyncio.run(delete(fake, stale))
    assert all(fake.doc(c, i) is None for c, i, _ in planted)
    assert fake.doc(live[0], live[1]) is not None and fake.doc(F.PRACTICALS, sid("practical:pendulum")) is not None
    assert asyncio.run(find_stale(fake)) == []
