"""Seed Cloud Firestore + Firebase Authentication with the Virtual Lab Manager demo data.

    # 1) dry run (default) — prints what would be written; read-only
    .venv/bin/python -m scripts.seed_firestore --project vlm-buildathon

    # 2) write it (asks you to type the project id to confirm)
    .venv/bin/python -m scripts.seed_firestore --project vlm-buildathon --apply

Same deterministic ids as the in-memory demo and database/002_seed.sql, so links and the demo story are identical.
Idempotent: documents are overwritten by id and Auth users are updated in place; nothing is ever deleted.
Timestamps are relative to "now", like the in-memory seed (re-running refreshes them).

Auth users: uid = users/{id}, email/password (demo1234), email_verified, display name, and custom claims
{role, department_id, app_uid} — firebase/firestore.rules and the API rely on those claims.

Credentials: Application Default Credentials (`gcloud auth application-default login` with a quota project).
Works against the emulators too (FIRESTORE_EMULATOR_HOST / FIREBASE_AUTH_EMULATOR_HOST).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

from app.db.firestore import ALL_COLLECTIONS, seed_documents, write_documents
from app.db.seed_data import DEMO_PASSWORD, build_seed
from app.models import UserRecord


def default_project() -> str:
    for var in ("FIREBASE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"):
        if os.environ.get(var):
            return os.environ[var]
    rc = Path(__file__).resolve().parents[2] / ".firebaserc"
    try:
        return json.loads(rc.read_text())["projects"]["default"]
    except (OSError, KeyError, ValueError):
        return ""


def claims_for(u: UserRecord) -> dict:
    return {"role": u.role, "department_id": u.department_id, "app_uid": u.id}


async def existing_counts(project: str, database: str) -> dict[str, int] | None:
    """Read-only: current document count per collection (None if the database can't be reached)."""
    try:
        from google.cloud import firestore

        db = firestore.AsyncClient(project=project, database=database)
        out = {}
        for col in ALL_COLLECTIONS:
            out[col] = int((await db.collection(col).count().get())[0][0].value)
        return out
    except Exception as e:  # noqa: BLE001 - informational only
        print(f"  (could not read existing counts: {type(e).__name__}: {str(e)[:160]})")
        return None


async def write_firestore(project: str, database: str, docs) -> int:
    from google.cloud import firestore

    db = firestore.AsyncClient(project=project, database=database)
    return await write_documents(db, docs)


def write_auth_users(project: str, users: list[UserRecord]) -> tuple[int, int]:
    import firebase_admin
    from firebase_admin import auth, credentials

    try:
        app = firebase_admin.get_app("vlm-seed")
    except ValueError:
        app = firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": project}, name="vlm-seed")
    created = updated = 0
    for u in users:
        fields = dict(email=u.email, password=DEMO_PASSWORD, email_verified=True, display_name=u.full_name,
                      disabled=False)
        try:
            auth.get_user(u.id, app=app)
            auth.update_user(u.id, app=app, **fields)
            updated += 1
        except auth.UserNotFoundError:
            try:
                auth.create_user(uid=u.id, app=app, **fields)
                created += 1
            except auth.EmailAlreadyExistsError:
                other = auth.get_user_by_email(u.email, app=app)
                sys.exit(f"Auth user {u.email} already exists with uid {other.uid}, expected {u.id}. "
                         "Delete or rename that account in the Firebase console, then re-run.")
        auth.set_custom_user_claims(u.id, claims_for(u), app=app)
    return created, updated


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=default_project(), help="GCP / Firebase project id")
    ap.add_argument("--database", default=os.environ.get("FIRESTORE_DATABASE", "(default)"))
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation (CI)")
    ap.add_argument("--skip-auth", action="store_true", help="write Firestore only, leave Firebase Auth untouched")
    ap.add_argument("--local-passwords", action="store_true",
                    help="also store PBKDF2 hashes in users/* so AUTH_PROVIDER=local works against Firestore")
    args = ap.parse_args()
    if not args.project:
        sys.exit("No project id: pass --project or set GOOGLE_CLOUD_PROJECT")

    seed = build_seed()
    docs = seed_documents(seed, include_password_hash=args.local_passwords)
    counts = Counter(col for col, _, _ in docs)
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")

    print(f"Project: {args.project}   database: {args.database}" + (f"   (EMULATOR {emulator})" if emulator else ""))
    print(f"Mode:    {'APPLY — will write' if args.apply else 'dry run — nothing is written'}\n")
    existing = asyncio.run(existing_counts(args.project, args.database))
    print(f"  {'collection':<22}{'to write':>9}{'existing':>10}")
    for col in ALL_COLLECTIONS:
        have = "-" if existing is None else existing.get(col, 0)
        print(f"  {col:<22}{counts.get(col, 0):>9}{have:>10}")
    print(f"  {'TOTAL':<22}{len(docs):>9}")
    roles = Counter(u.role for u in seed.users)
    print(f"\nFirebase Auth: {len(seed.users)} users ({dict(roles)}), password from DEMO_PASSWORD, "
          "custom claims {role, department_id, app_uid}" + ("  [skipped: --skip-auth]" if args.skip_auth else ""))
    print(f"users/* password_hash: {'PBKDF2 (local auth also works)' if args.local_passwords else 'empty (Firebase Auth only)'}")

    if not args.apply:
        print("\nDry run complete. Re-run with --apply to write.")
        return
    if not args.yes:
        typed = input(f"\nType the project id ({args.project}) to write to it: ").strip()
        if typed != args.project:
            sys.exit("Aborted — nothing written.")

    n = asyncio.run(write_firestore(args.project, args.database, docs))
    print(f"Firestore: wrote {n} documents")
    if not args.skip_auth:
        created, updated = write_auth_users(args.project, seed.users)
        print(f"Firebase Auth: created {created}, updated {updated} users (claims set on all {created + updated})")
    print("Done.")


if __name__ == "__main__":
    main()
