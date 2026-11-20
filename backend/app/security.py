"""Password hashing (PBKDF2-SHA256, stdlib), JWT issuance/validation and RBAC dependencies."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.db.base import Repository
from app.models import Role, UserRecord, utcnow

_PBKDF2_ITERATIONS = 310_000
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iterations)
        )
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def create_access_token(user: UserRecord, settings: Settings) -> str:
    now = utcnow()
    payload = {
        "sub": user.id,
        "role": user.role,
        "dept": user.department_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


RepoDep = Annotated[Repository, Depends(get_repo)]


async def get_current_user(
    repo: RepoDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserRecord:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    if settings.auth_provider == "firebase":
        return await _firebase_user(repo, creds.credentials, settings, unauthorized)
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except jwt.PyJWTError:
        raise unauthorized
    user = await repo.get_user(str(payload.get("sub", "")))
    if user is None:
        raise unauthorized
    # role in the token must still match the stored role (role changes invalidate tokens)
    if payload.get("role") != user.role:
        raise unauthorized
    return user


async def _firebase_user(repo: Repository, token: str, settings: Settings, unauthorized: HTTPException) -> UserRecord:
    """Firebase ID token -> our user. Identity comes from the `app_uid` custom claim (set at provisioning),
    falling back to the Firebase uid, which equals users/{id} for provisioned accounts."""
    from app import firebase_auth

    try:
        claims = await asyncio.to_thread(firebase_auth.verify_id_token, token, settings)
    except firebase_auth.FirebaseTokenExpired:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except firebase_auth.FirebaseTokenInvalid:
        raise unauthorized
    user_id = str(claims.get("app_uid") or claims.get("uid") or claims.get("sub") or "")
    user = await repo.get_user(user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=403, detail="This sign-in has no Virtual Lab Manager account")
    # the role claim must still match the stored role (role changes invalidate tokens until claims are updated)
    if claims.get("role") != user.role:
        raise unauthorized
    return user


CurrentUser = Annotated[UserRecord, Depends(get_current_user)]


def require_roles(*roles: Role):
    async def checker(user: CurrentUser) -> UserRecord:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"This action requires role: {' or '.join(roles)}")
        return user

    return checker


StudentUser = Annotated[UserRecord, Depends(require_roles("student"))]
FacultyUser = Annotated[UserRecord, Depends(require_roles("faculty", "hod"))]
HodUser = Annotated[UserRecord, Depends(require_roles("hod"))]
