from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.db.seed_data import DEMO_STUDENT, FACULTY, HOD, email_for
from app.deps import Svc
from app.schemas import DemoAccount, LoginRequest, LoginResponse, UserOut
from app.security import CurrentUser, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Failed-login throttle for local auth (in Firebase mode, Firebase Authentication throttles sign-ins itself).
# Keyed by client IP + email, so someone hammering a public demo email can't lock everyone else out of it.
# In-process: each Cloud Run instance keeps its own counts.
LOGIN_MAX_FAILURES = 10
LOGIN_FAILURE_WINDOW_S = 600.0
_PRUNE_ABOVE_KEYS = 10_000
_failed_logins: dict[tuple[str, str], deque[float]] = defaultdict(deque)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Verified against when the email is unknown, so response time doesn't reveal which emails have accounts."""
    return hash_password(secrets.token_urlsafe(16))


def _login_key(request: Request, email: str) -> tuple[str, str]:
    host = request.client.host if request.client else "unknown"
    return host, email.strip().lower()


def _recent_failures(key: tuple[str, str], now: float) -> deque[float]:
    if len(_failed_logins) > _PRUNE_ABOVE_KEYS:
        for k in [k for k, q in _failed_logins.items() if not q or now - q[-1] > LOGIN_FAILURE_WINDOW_S]:
            del _failed_logins[k]
    q = _failed_logins[key]
    while q and now - q[0] > LOGIN_FAILURE_WINDOW_S:
        q.popleft()
    return q


def user_out(u) -> UserOut:
    return UserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role,
                   department_id=u.department_id, roll_number=u.roll_number)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, svc: Svc, settings: Annotated[Settings, Depends(get_settings)]):
    if settings.auth_provider != "local":
        raise HTTPException(status_code=400, detail="This deployment uses Firebase Authentication: sign in with Firebase "
                                                    "and send the Firebase ID token as the Bearer token.")
    key = _login_key(request, body.email)
    now = time.monotonic()
    failures = _recent_failures(key, now)
    if len(failures) >= LOGIN_MAX_FAILURES:
        retry_after = int(LOGIN_FAILURE_WINDOW_S - (now - failures[0])) + 1
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again in a few minutes.",
                            headers={"Retry-After": str(retry_after)})

    user = await svc.repo.get_user_by_email(body.email)
    # verify in a thread: PBKDF2 is CPU-bound and would block the event loop
    encoded = user.password_hash if user is not None else _dummy_hash()
    ok = await asyncio.to_thread(verify_password, body.password, encoded) and user is not None
    if not ok:
        failures.append(now)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _failed_logins.pop(key, None)
    return LoginResponse(access_token=create_access_token(user, settings), user=user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user_out(user)


@router.get("/demo-accounts", response_model=list[DemoAccount])
async def demo_accounts(settings: Annotated[Settings, Depends(get_settings)]):
    if not settings.demo_mode:
        return []
    pwd = settings.demo_password
    return [
        DemoAccount(role="student", email=email_for(DEMO_STUDENT), full_name=DEMO_STUDENT, password=pwd),
        DemoAccount(role="faculty", email=email_for(FACULTY[0]), full_name=FACULTY[0], password=pwd),
        DemoAccount(role="hod", email=email_for(HOD), full_name=HOD, password=pwd),
    ]
