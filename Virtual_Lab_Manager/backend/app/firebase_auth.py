"""Firebase Authentication: verify ID tokens sent by the browser (AUTH_PROVIDER=firebase).

Verification needs only the project id and Google's public signing certificates (cached by the SDK); it does not
read or write any Firebase data. Custom claims {role, department_id, app_uid} are set when accounts are provisioned
(backend/scripts/seed_firestore.py).
"""

from __future__ import annotations

import threading
from typing import Any

from app.config import Settings

_APP_NAME = "vlm"
_lock = threading.Lock()


class FirebaseTokenExpired(Exception):
    pass


class FirebaseTokenInvalid(Exception):
    pass


def firebase_app(settings: Settings) -> Any:
    import firebase_admin

    with _lock:
        try:
            return firebase_admin.get_app(_APP_NAME)
        except ValueError:
            # No credential is needed to verify ID tokens; ADC is used lazily for anything else.
            return firebase_admin.initialize_app(options={"projectId": settings.gcp_project}, name=_APP_NAME)


def verify_id_token(token: str, settings: Settings) -> dict:
    """Blocking (may fetch Google's public certs) — call via asyncio.to_thread. Returns the decoded claims."""
    from firebase_admin import auth

    try:
        return auth.verify_id_token(token, app=firebase_app(settings), check_revoked=False, clock_skew_seconds=10)
    except auth.ExpiredIdTokenError as e:
        raise FirebaseTokenExpired(str(e)) from e
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, ValueError) as e:
        raise FirebaseTokenInvalid(str(e)) from e
