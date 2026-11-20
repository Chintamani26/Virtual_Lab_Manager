"""Run every API suite against each storage backend.

`memory` is the seeded in-memory store; `firestore` is the real FirestoreRepository on top of an in-process
fake client (tests/fake_firestore.py) seeded through the same function the seed script uses.
Limit with e.g. `VLM_TEST_STORAGES=memory pytest`.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.db.base import Repository

STORAGES = [s.strip() for s in os.environ.get("VLM_TEST_STORAGES", "memory,firestore").split(",") if s.strip()]


def make_fake_firestore_repo():
    from app.db.firestore import FirestoreRepository, seed_documents, write_documents
    from app.db.seed_data import build_seed
    from tests.fake_firestore import FakeFirestore

    fake = FakeFirestore()
    asyncio.run(write_documents(fake, seed_documents(build_seed(), include_password_hash=True)))
    return FirestoreRepository(fake, transact=fake.run_transaction)


def make_repo(storage: str) -> Repository | None:
    """None => create_app builds the default (memory) repository from settings."""
    if storage == "memory":
        return None
    if storage == "firestore":
        return make_fake_firestore_repo()
    raise ValueError(f"unknown test storage {storage!r}")


@pytest.fixture(scope="module", params=STORAGES)
def storage(request) -> str:
    return request.param
