"""READ-ONLY check that every Firestore query this app issues is served by the deployed indexes.

    .venv/bin/python -m scripts.check_firestore_indexes --project vlm-buildathon

1. Calls every *read* method of FirestoreRepository against the real database (no writes), capturing the exact
   query shapes it issues, plus the browser's exam_live listener shapes and the server's staff fan-out query.
2. For each shape: Firestore query EXPLAIN (analyze=False — plans the query, reads no documents) to report the
   index it uses, then the query itself with limit(1) to prove it doesn't fail with "requires an index".
3. Compares composite indexes actually used with firebase/firestore.indexes.json (missing / unused).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from google.api_core import exceptions as gexc
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.query_profile import ExplainOptions

from app.db import firestore as F
from app.db.firestore import FirestoreRepository
from app.db.seed_data import email_for, sid
from app.models import utcnow

ROOT = Path(__file__).resolve().parents[2]


def build(db, collection: str, filters, order=None, limit=None, select=None):
    q: Any = db.collection(collection)
    for f, op, v in filters:
        q = q.where(filter=FieldFilter(f, op, v))
    if select is not None:
        q = q.select(select)
    if order is not None:
        q = q.order_by(order[0], direction=order[1])
    return q.limit(limit or 1)


def shape_key(collection, filters, order) -> str:
    parts = [f"{f} {op}" for f, op, _ in filters] + ([f"order {order[0]} {order[1][:4]}"] if order else [])
    return f"{collection}: " + ", ".join(parts) if parts else f"{collection}: (all)"


def index_fields(properties: str) -> tuple[str, ...]:
    # "(practical_id ASC, created_at DESC, __name__ DESC)" -> ("practical_id", "created_at")
    return tuple(p.split()[0] for p in properties.strip("()").split(", ") if p and not p.startswith("__name__"))


async def capture_shapes(repo: FirestoreRepository) -> list[tuple]:
    shapes: list[tuple] = []
    orig = FirestoreRepository._query

    async def recording(self, collection, filters=(), *, order=None, limit=None, select=None):
        filters = list(filters)
        shapes.append((collection, filters, order, select))
        return await orig(self, collection, filters, order=order, limit=limit, select=select)

    FirestoreRepository._query = recording  # type: ignore[method-assign]
    try:
        stu, fac, dept = sid("user:" + email_for("Aarav Sharma")), sid("user:" + email_for("Meera Kulkarni")), sid("dept:ce")
        bst, cs201 = sid("practical:bst"), sid("course:CS201")
        r = repo
        await r.get_user_by_email("aarav.sharma@demo.edu")
        await r.list_users(dept, "student"); await r.list_users(dept)
        await r.list_courses(department_id=dept); await r.list_courses(faculty_id=fac)
        await r.list_courses(student_id=stu); await r.list_courses()
        await r.list_enrollments([cs201])
        await r.list_practicals([cs201]); await r.list_practicals([cs201], published_only=True)
        await r.list_submissions(practical_ids=[bst]); await r.list_submissions(student_id=stu)
        await r.list_submissions(practical_ids=[bst], student_id=stu); await r.list_submissions()
        await r.get_latest_execution(bst, stu, "test")
        await r.list_execution_logs([bst]); await r.list_execution_logs([bst], since=utcnow() - timedelta(days=30))
        await r.list_hint_logs(practical_ids=[bst]); await r.list_hint_logs(student_id=stu)
        await r.list_hint_logs(practical_ids=[bst], student_id=stu)
        await r.list_proctor_events(bst, stu); await r.list_practical_proctor_events(bst)
        await r.list_proctor_sessions(bst, stu); await r.list_practical_proctor_sessions(bst)
        await r.list_exam_attempts([bst])
    finally:
        FirestoreRepository._query = orig  # type: ignore[method-assign]
    # not reachable through read-only repository calls
    shapes.append((F.LIVE, [("course_id", "==", cs201), ("status", "in", ["active", "locked"])], None, None))  # faculty fan-out
    shapes.append((F.LIVE, [("practical_id", "==", bst), ("staff_ids", "array_contains", fac)], None, None))   # monitor listener
    shapes.append((F.LIVE, [("staff_ids", "array_contains", fac), ("status", "==", "locked")], None, None))    # alerts bell
    shapes.append((F.LIVE, [("student_id", "==", stu)], None, None))                                           # student list
    return shapes


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--database", default="(default)")
    args = ap.parse_args()

    db = firestore.AsyncClient(project=args.project, database=args.database)
    shapes = await capture_shapes(FirestoreRepository(db))

    seen: dict[str, tuple] = {}
    for s in shapes:
        seen.setdefault(shape_key(s[0], s[1], s[2]), s)

    used_composites: set[tuple[str, tuple[str, ...]]] = set()
    failures = 0
    print(f"{'query shape':<92} result / index used")
    for key, (collection, filters, order, select) in seen.items():
        q = build(db, collection, filters, order, 1, select)
        try:
            plan = (await q.get(explain_options=ExplainOptions(analyze=False))).get_explain_metrics().plan_summary
            idx = [i.get("properties", "") for i in plan.indexes_used]
            await q.get()  # the real query, limit(1)
            label = "; ".join(idx) or "(no index)"
            for props in idx:
                fields = index_fields(props)
                if len(fields) >= 2:
                    used_composites.add((collection, fields))
            print(f"OK   {key:<87} {label}")
        except gexc.FailedPrecondition as e:
            failures += 1
            link = re.search(r"https://\S+", str(e))
            print(f"NEEDS INDEX {key}\n     {link.group(0) if link else str(e)[:200]}")
        except gexc.GoogleAPICallError as e:
            failures += 1
            print(f"ERROR {key}: {type(e).__name__}: {str(e)[:200]}")

    declared = set()
    for ix in json.loads((ROOT / "firebase/firestore.indexes.json").read_text())["indexes"]:
        declared.add((ix["collectionGroup"], tuple(f["fieldPath"] for f in ix["fields"])))
    print("\nComposite indexes used by queries but NOT declared:", sorted(used_composites - declared) or "none")
    print("Composite indexes declared but not used by any query:", sorted(declared - used_composites) or "none")
    print(f"\n{len(seen)} query shapes checked, {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
