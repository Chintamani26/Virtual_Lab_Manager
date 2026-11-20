"""Security hardening tests: startup validation, headers, redaction, path traversal, and CSV injection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.client import AIClient
from app.config import DEV_JWT_SECRET, Settings, validate_settings
from app.main import create_app
from app.routers.hod import _csv_safe
from app.schemas import FilesBody


def test_validate_settings_rejects_weak_production_jwt_secret():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_settings(Settings(app_env="production", auth_provider="local", jwt_secret=DEV_JWT_SECRET))
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_settings(Settings(app_env="production", auth_provider="local", jwt_secret="too-short"))


def test_validate_settings_rejects_wildcard_cors_in_production():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_settings(
            Settings(
                app_env="production",
                auth_provider="local",
                jwt_secret="x" * 48,
                cors_origins="*",
            )
        )


def test_validate_settings_requires_gcp_project_for_firestore():
    with pytest.raises(RuntimeError, match="STORAGE=firestore"):
        validate_settings(Settings(storage="firestore", google_cloud_project="", firebase_project_id=""))


def test_security_headers_and_health_redaction_in_production():
    settings = Settings(
        app_env="production",
        storage="memory",
        auth_provider="local",
        jwt_secret="p" * 48,
        cors_origins="https://app.example.edu",
        allow_local_execution_in_production=True,
    )
    app = create_app(settings)
    app.state.services.ai.last_error = "gemini: RuntimeError: internal upstream detail"
    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert res.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert res.json()["ai"]["last_error"] is None


def test_ai_client_redacts_api_keys_and_tokens():
    client = AIClient(Settings(gemini_api_key=""))
    client._api_key = "fake-secret-value-12345"
    redacted = client._redact("request failed key=abc123 Authorization: Bearer tok999 fake-secret-value-12345")
    assert "fake-secret-value-12345" not in redacted
    assert "abc123" not in redacted
    assert "tok999" not in redacted


@pytest.mark.parametrize("bad_name", ["../main.py", "a/../../etc/passwd", "dir/", "dir//file.py", "__name__"])
def test_files_body_rejects_path_traversal_and_reserved_names(bad_name: str):
    with pytest.raises(ValidationError):
        FilesBody(files={bad_name: "print(1)"})


def test_csv_safe_neutralizes_formula_prefixes():
    row = {"practical_title": "=CMD|' /C calc'!A0", "faculty_name": "+Prof", "course_code": "CS201", "enrolled": 24}
    safe = _csv_safe(row)
    assert safe["practical_title"].startswith("'")
    assert safe["faculty_name"].startswith("'")
    assert safe["course_code"] == "CS201"
    assert safe["enrolled"] == 24
