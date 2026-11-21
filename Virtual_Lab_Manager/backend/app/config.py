"""Application settings, loaded from environment variables / .env."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder used when JWT_SECRET is unset, so local development works out of the box.
# validate_settings() refuses it (and any short secret) when APP_ENV=production with local auth.
DEV_JWT_SECRET = "dev-only-change-me-please-32-bytes-min!!"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "Virtual Lab Manager API"

    # --- Security ---
    jwt_secret: str = Field(default=DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000"  # comma separated

    # --- Storage ---
    # auto: PostgreSQL when DATABASE_URL is set, else the in-memory demo store (seeded, resets on restart).
    # firestore: Cloud Firestore (docs/FIRESTORE_DESIGN.md) in GOOGLE_CLOUD_PROJECT / FIREBASE_PROJECT_ID.
    storage: Literal["auto", "memory", "postgres", "firestore"] = "auto"
    # postgresql://user:pass@host:5432/dbname => AlloyDB / Cloud SQL / Supabase.
    database_url: str = ""
    google_cloud_project: str = ""
    firebase_project_id: str = ""
    firestore_database: str = "(default)"
    demo_mode: bool = True  # exposes /api/auth/demo-accounts + one-click logins
    demo_password: str = "demo1234"  # override via DEMO_PASSWORD env var

    # --- Auth ---
    # local: our own PBKDF2 passwords + HS256 JWTs (demo / tests).
    # firebase: browsers sign in with Firebase Authentication; the API verifies Firebase ID tokens.
    auth_provider: Literal["local", "firebase"] = "local"

    # --- Execution engine ---
    # auto: Judge0 if JUDGE0_URL configured, else local subprocess (dev only).
    execution_engine: Literal["auto", "judge0", "local"] = "auto"
    judge0_url: str = ""  # e.g. https://judge0-ce.p.rapidapi.com or http://judge0:2358
    judge0_api_key: str = ""  # RapidAPI key or self-hosted X-Auth-Token
    judge0_rapidapi_host: str = ""  # e.g. judge0-ce.p.rapidapi.com (set when using RapidAPI)
    judge0_python_language_id: int = 71  # Judge0 CE "Python (3.8.1)"
    execution_timeout_seconds: float = 8.0
    allow_local_execution_in_production: bool = False

    # --- Google AI ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemma_model: str = "gemma-4-26b-a4b-it"
    ai_timeout_seconds: float = 25.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def storage_backend(self) -> str:
        if self.storage != "auto":
            return self.storage
        return "postgres" if self.database_url else "memory"

    @property
    def gcp_project(self) -> str:
        return self.firebase_project_id or self.google_cloud_project


def validate_settings(settings: Settings) -> None:
    """Fail fast at startup on configuration that would be insecure or broken at runtime.

    Error messages name the variable but never echo its value.
    """
    if settings.app_env == "production" and settings.auth_provider == "local":
        if settings.jwt_secret == DEV_JWT_SECRET or len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            raise RuntimeError(
                f"JWT_SECRET must be a random string of at least {MIN_JWT_SECRET_LENGTH} characters in production "
                "(e.g. `openssl rand -base64 48`)"
            )
    if settings.app_env == "production":
        if "*" in settings.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must list explicit origins in production (wildcard '*' is not allowed)")
    if settings.auth_provider == "firebase" and not settings.gcp_project:
        raise RuntimeError("AUTH_PROVIDER=firebase needs GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID")
    if settings.storage_backend == "firestore" and not settings.gcp_project:
        raise RuntimeError("STORAGE=firestore needs GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID")


@lru_cache
def get_settings() -> Settings:
    return Settings()
