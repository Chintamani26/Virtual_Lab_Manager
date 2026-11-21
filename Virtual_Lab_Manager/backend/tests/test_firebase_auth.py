"""AUTH_PROVIDER=firebase: the API trusts Firebase ID tokens (verification monkeypatched — no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import firebase_auth
from app.config import Settings
from app.db.seed_data import email_for, sid
from app.main import create_app
from tests.conftest import make_repo


def uid(name: str) -> str:
    return sid("user:" + email_for(name))


CLAIMS = {
    "aarav": {"uid": uid("Aarav Sharma"), "app_uid": uid("Aarav Sharma"), "role": "student"},
    "meera": {"uid": uid("Meera Kulkarni"), "app_uid": uid("Meera Kulkarni"), "role": "faculty"},
    "stale-role": {"uid": uid("Aarav Sharma"), "app_uid": uid("Aarav Sharma"), "role": "faculty"},
    "no-claims": {"uid": uid("Aarav Sharma")},                     # provisioned uid but claims not set yet
    "stranger": {"uid": "google-oauth2|someone", "role": "student"},
}


def fake_verify(token: str, settings: Settings) -> dict:
    if token == "expired":
        raise firebase_auth.FirebaseTokenExpired("expired")
    if token not in CLAIMS:
        raise firebase_auth.FirebaseTokenInvalid("bad signature")
    return CLAIMS[token]


@pytest.fixture(scope="module")
def client(storage):
    mp = pytest.MonkeyPatch()
    mp.setattr(firebase_auth, "verify_id_token", fake_verify)
    settings = Settings(_env_file=None, app_env="test", gemini_api_key="", database_url="", execution_engine="local",
                        auth_provider="firebase", firebase_project_id="vlm-test")
    with TestClient(create_app(settings, repo=make_repo(storage))) as c:
        yield c
    mp.undo()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_health_reports_firebase(client):
    body = client.get("/api/health").json()
    assert body["auth_provider"] == "firebase" and body["firebase_project"] == "vlm-test"


def test_valid_tokens_map_to_users(client):
    me = client.get("/api/auth/me", headers=bearer("aarav")).json()
    assert me["email"] == "aarav.sharma@demo.edu" and me["role"] == "student"
    assert client.get("/api/student/dashboard", headers=bearer("aarav")).status_code == 200
    assert client.get("/api/faculty/dashboard", headers=bearer("meera")).status_code == 200
    assert client.get("/api/faculty/dashboard", headers=bearer("aarav")).status_code == 403


def test_rejections(client):
    assert client.get("/api/auth/me", headers=bearer("stale-role")).status_code == 401   # role changed since issue
    assert client.get("/api/auth/me", headers=bearer("no-claims")).status_code == 401    # claims not provisioned
    assert client.get("/api/auth/me", headers=bearer("stranger")).status_code == 403     # no account here
    assert client.get("/api/auth/me", headers=bearer("forged")).status_code == 401
    expired = client.get("/api/auth/me", headers=bearer("expired"))
    assert expired.status_code == 401 and "expired" in expired.json()["detail"]
    assert client.get("/api/auth/me").status_code == 401


def test_password_login_is_disabled(client):
    r = client.post("/api/auth/login", json={"email": "aarav.sharma@demo.edu", "password": "demo1234"})
    assert r.status_code == 400 and "Firebase" in r.json()["detail"]
    assert len(client.get("/api/auth/demo-accounts").json()) == 3   # still listed for one-click Firebase sign-in


def test_firebase_mode_requires_a_project():
    with pytest.raises(RuntimeError):
        create_app(Settings(_env_file=None, app_env="test", auth_provider="firebase", gemini_api_key="",
                            database_url="", google_cloud_project="", firebase_project_id=""))
