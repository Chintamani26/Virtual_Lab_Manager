"""Login hardening: failed-login throttle, unknown-email handling, and demo-password consistency."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db.seed_data import DEMO_PASSWORD, email_for
from app.main import create_app
from app.routers import auth as auth_router


@pytest.fixture()
def client():
    auth_router._failed_logins.clear()
    app = create_app(Settings(app_env="test", jwt_secret="t" * 48, storage="memory"))
    with TestClient(app) as c:
        yield c
    auth_router._failed_logins.clear()


def _login(c: TestClient, email: str, password: str):
    return c.post("/api/auth/login", json={"email": email, "password": password})


def test_demo_password_has_a_single_source():
    # Seeded password hashes and /api/auth/demo-accounts must agree, or the one-click logins fail with 401.
    assert DEMO_PASSWORD == get_settings().demo_password


def test_one_click_demo_accounts_can_sign_in(client):
    accounts = client.get("/api/auth/demo-accounts").json()
    assert len(accounts) == 3
    for acct in accounts:
        assert _login(client, acct["email"], acct["password"]).status_code == 200


def test_unknown_email_gets_the_same_401_as_a_wrong_password(client):
    unknown = _login(client, "nobody@demo.edu", "whatever")
    wrong = _login(client, email_for("Aarav Sharma"), "wrong-password")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_failed_logins_are_throttled_per_client_and_email(client):
    email = email_for("Meera Kulkarni")
    for _ in range(auth_router.LOGIN_MAX_FAILURES):
        assert _login(client, email, "wrong-password").status_code == 401
    blocked = _login(client, email, DEMO_PASSWORD)  # even the right password is refused while throttled
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # another account from the same client is unaffected
    assert _login(client, email_for("Aarav Sharma"), DEMO_PASSWORD).status_code == 200
    # the same account from another client address is unaffected (no lockout of a shared demo login)
    other = TestClient(client.app, client=("203.0.113.7", 50000))
    assert _login(other, email, DEMO_PASSWORD).status_code == 200


def test_successful_login_resets_the_failure_count(client):
    email = email_for("Aarav Sharma")
    for _ in range(auth_router.LOGIN_MAX_FAILURES - 1):
        _login(client, email, "wrong-password")
    assert _login(client, email, DEMO_PASSWORD).status_code == 200
    assert _login(client, email, "wrong-password").status_code == 401  # count restarted, not blocked
