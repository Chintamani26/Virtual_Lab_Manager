"""Virtual Lab Manager API — FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai.analyst import HodAnalyst
from app.ai.briefing import DepartmentBriefingGenerator
from app.ai.difficulties import LearningDifficultyAnalyzer
from app.ai.practical_gen import PracticalGenerator
from app.ai.teaching import TeachingMaterialGenerator
from app.ai.client import AIClient
from app.ai.grader import RubricGrader
from app.ai.integrity import IntegrityAnalyzer
from app.ai.linter import HybridLinter
from app.ai.testgen import TestGenerator
from app.ai.tutor import SocraticTutor
from app.ai.tutor_chat import LabTutor
from app.config import Settings, get_settings, validate_settings
from app.db.base import Repository
from app.deps import Services
from app.execution.runners import build_runner
from app.execution.service import ExecutionService
from app.routers import ai_tools, auth, faculty, hod, student, tutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vlm")


def build_repository(settings: Settings) -> Repository:
    backend = settings.storage_backend
    if backend == "firestore":
        from app.db.firestore import FirestoreRepository

        return FirestoreRepository.from_settings(settings)
    if backend == "postgres":
        if not settings.database_url:
            raise RuntimeError("STORAGE=postgres needs DATABASE_URL")
        from app.db.postgres import PostgresRepository

        return PostgresRepository(settings.database_url)
    from app.db.memory import MemoryRepository
    from app.db.seed_data import build_seed

    return MemoryRepository(build_seed())


def build_services(settings: Settings, repo: Repository) -> Services:
    ai = AIClient(settings)
    tutor = SocraticTutor(ai)
    execution = ExecutionService(build_runner(settings))
    return Services(
        repo=repo,
        execution=execution,
        ai=ai,
        tutor=tutor,
        lab_tutor=LabTutor(ai, tutor),
        grader=RubricGrader(ai),
        linter=HybridLinter(ai),
        testgen=TestGenerator(ai),
        analyst=HodAnalyst(ai),
        integrity=IntegrityAnalyzer(ai),
        practical_gen=PracticalGenerator(ai, execution),
        teaching=TeachingMaterialGenerator(ai),
        difficulties=LearningDifficultyAnalyzer(ai),
        briefing=DepartmentBriefingGenerator(ai),
    )


def create_app(settings: Settings | None = None, repo: Repository | None = None) -> FastAPI:
    settings = settings or get_settings()
    validate_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await app.state.repo.connect()
        log.info(
            "storage=%s auth=%s execution=%s ai=%s (gemini=%s, gemma=%s)",
            app.state.repo.name, settings.auth_provider, app.state.services.execution.engine_name,
            "on" if settings.ai_enabled else "fallback", settings.gemini_model, settings.gemma_model,
        )
        yield
        await app.state.repo.close()

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.repo = repo or build_repository(settings)
    app.state.services = build_services(settings, app.state.repo)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Exam-Session", "X-SEB-Page-Url", "X-SEB-ConfigKey-Hash",
                       "X-SafeExamBrowser-ConfigKeyHash"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.get("/api/health", tags=["meta"])
    async def health():
        svc: Services = app.state.services
        return {
            "status": "ok",
            "storage": app.state.repo.name,
            "auth_provider": settings.auth_provider,
            "firebase_project": settings.gcp_project or None,
            "execution_engine": svc.execution.engine_name,
            "ai": {
                "gemini_model": settings.gemini_model,
                "gemma_model": settings.gemma_model,
                "enabled": settings.ai_enabled,
                "last_error": None if settings.app_env == "production" else svc.ai.last_error,
            },
        }

    for r in (auth.router, student.router, tutor.router, faculty.router, hod.router, ai_tools.faculty_router,
              ai_tools.hod_router):
        app.include_router(r)
    return app


app = create_app()
