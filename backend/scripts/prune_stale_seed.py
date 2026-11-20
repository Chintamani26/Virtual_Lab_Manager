"""Remove Firestore documents left behind by earlier versions of the demo seed.

`seed_firestore` overwrites documents by id and never deletes, so after the 2026-11-20 changes an existing project
still holds documents the current seed no longer has:

  * courses/<DS301> and its 12 enrolments, and the 24 CS305 enrolments (course line-up change)
  * the retired labs Half Adder, Full Adder (EE210) and Exploratory Analysis (MA201): the practical documents and every
    draft, submission, execution log, hint, proctoring session/event and exam record that points at them
  * documents of the redesigned Pendulum lab (notebook -> virtual experiment) that the new seed doesn't write,
    e.g. extra practice runs from the notebook version

Everything else is left alone: live work on any other lab is never touched. Run it AFTER re-seeding:

    # 1) dry run (default) — read-only: lists what would be deleted
    .venv/bin/python -m scripts.prune_stale_seed --project vlm-buildathon

    # 2) delete (asks you to type the project id to confirm)
    .venv/bin/python -m scripts.prune_stale_seed --project vlm-buildathon --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from app.db.firestore import (
    ATTEMPTS,
    COURSES,
    DRAFTS,
    ENROLLMENTS,
    EVENTS,
    EXECUTIONS,
    HINTS,
    LIVE,
    PRACTICALS,
    SESSIONS,
    SUBMISSIONS,
    pair_id,
    seed_documents,
)
from app.db.seed_data import STUDENTS, build_seed, email_for, sid
from scripts.seed_firestore import default_project

RETIRED_PRACTICALS = ("half_adder", "full_adder", "eda")
REDESIGNED_PRACTICALS = ("pendulum",)
PER_PRACTICAL = (DRAFTS, SUBMISSIONS, EXECUTIONS, HINTS, SESSIONS, EVENTS, ATTEMPTS, LIVE)
BATCH = 450


def retired_course_docs() -> list[tuple[str, str]]:
    students = [sid(f"user:{email_for(n)}") for n in STUDENTS]
    ds301, cs305 = sid("course:DS301"), sid("course:CS305")
    docs = [(COURSES, ds301)]
    docs += [(ENROLLMENTS, pair_id(ds301, s)) for s in students[:12]]
    docs += [(ENROLLMENTS, pair_id(cs305, s)) for s in students]
    return docs


async def find_stale(client: Any) -> list[tuple[str, str]]:
    """Read-only: (collection, document id) of every stale document that exists."""
    seeded = {(col, doc_id) for col, doc_id, _ in seed_documents(build_seed(), include_password_hash=False)}
    stale: list[tuple[str, str]] = []
    for col, doc_id in retired_course_docs():
        if (await client.collection(col).document(doc_id).get()).exists:
            stale.append((col, doc_id))
    for slug in RETIRED_PRACTICALS + REDESIGNED_PRACTICALS:
        pid = sid(f"practical:{slug}")
        if slug in RETIRED_PRACTICALS and (await client.collection(PRACTICALS).document(pid).get()).exists:
            stale.append((PRACTICALS, pid))
        for col in PER_PRACTICAL:
            q = client.collection(col).where(filter=FieldFilter("practical_id", "==", pid))
            async for snap in q.stream():
                if slug in RETIRED_PRACTICALS or (col, snap.id) not in seeded:
                    stale.append((col, snap.id))
    return stale


async def delete(client: Any, docs: list[tuple[str, str]]) -> int:
    for i in range(0, len(docs), BATCH):
        batch = client.batch()
        for col, doc_id in docs[i:i + BATCH]:
            batch.delete(client.collection(col).document(doc_id))
        await batch.commit()
    return len(docs)


async def run(project: str, database: str, apply: bool) -> None:
    from google.cloud import firestore

    client = firestore.AsyncClient(project=project, database=database)
    stale = await find_stale(client)
    counts = Counter(col for col, _ in stale)
    print(f"{len(stale)} stale documents")
    for col, n in sorted(counts.items()):
        print(f"  {col:<22}{n:>6}")
    if not apply:
        print("\nDry run complete. Re-run with --apply to delete." if stale else "\nNothing to delete.")
        return
    if stale:
        print(f"Deleted {await delete(client, stale)} documents.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=default_project(), help="GCP / Firebase project id")
    ap.add_argument("--database", default=os.environ.get("FIRESTORE_DATABASE", "(default)"))
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()
    if not args.project:
        sys.exit("No project id: pass --project or set GOOGLE_CLOUD_PROJECT")
    print(f"Project: {args.project}   database: {args.database}")
    if args.apply:
        typed = input(f"Type the project id ({args.project}) to delete from it: ").strip()
        if typed != args.project:
            sys.exit("Aborted — nothing deleted.")
    asyncio.run(run(args.project, args.database, args.apply))


if __name__ == "__main__":
    main()
