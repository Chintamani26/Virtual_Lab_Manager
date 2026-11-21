"""A small in-process stand-in for `google.cloud.firestore.AsyncClient` — just the surface FirestoreRepository uses.

It deliberately enforces the Firestore rules that bite in production, so the test-suite catches them without a
real database: no nested arrays, no `__reserved__` field names, no empty keys, ≤ 30 values in `in` filters,
≤ 500 writes per batch, ~1 MiB per document, and order_by excluding documents that lack the field.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from datetime import datetime
from typing import Any

_RESERVED = re.compile(r"^__.*__$")
MAX_DOC_BYTES = 1_048_576


class FirestoreLimitError(ValueError):
    pass


def _validate(value: Any, path: str = "", in_array: bool = False) -> int:
    """Returns an approximate encoded size; raises on values Firestore would reject."""
    if value is None or isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        if isinstance(value, int) and not -(2 ** 63) <= value < 2 ** 63:
            raise FirestoreLimitError(f"{path}: integer out of 64-bit range")
        return 8
    if isinstance(value, str):
        return len(value.encode("utf-8")) + 1
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, datetime):
        return 8
    if isinstance(value, dict):
        size = 0
        for k, v in value.items():
            if not isinstance(k, str) or not k:
                raise FirestoreLimitError(f"{path}: field names must be non-empty strings")
            if _RESERVED.match(k):
                raise FirestoreLimitError(f"{path}.{k}: field names matching __.*__ are reserved")
            size += len(k) + 1 + _validate(v, f"{path}.{k}")
        return size
    if isinstance(value, list):
        if in_array:
            raise FirestoreLimitError(f"{path}: arrays cannot directly contain arrays")
        return sum(_validate(v, f"{path}[]", in_array=True) for v in value)
    raise FirestoreLimitError(f"{path}: unsupported type {type(value).__name__}")


class FakeSnapshot:
    def __init__(self, ref: "FakeDocRef", data: dict | None) -> None:
        self.reference, self.id, self._data = ref, ref.id, data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data)


class FakeDocRef:
    def __init__(self, db: "FakeFirestore", collection: str, doc_id: str) -> None:
        if not doc_id or "/" in doc_id:
            raise FirestoreLimitError(f"invalid document id {doc_id!r}")
        self._db, self.collection, self.id = db, collection, doc_id

    async def get(self, transaction: Any = None) -> FakeSnapshot:
        return FakeSnapshot(self, self._db._store.get(self.collection, {}).get(self.id))

    async def set(self, data: dict) -> None:
        self._db._write(self, data)

    async def update(self, fields: dict) -> None:
        self._db._update(self, fields)


class FakeQuery:
    def __init__(self, db: "FakeFirestore", collection: str) -> None:
        self._db, self._collection = db, collection
        self._filters: list[tuple[str, str, Any]] = []
        self._order: list[tuple[str, str]] = []
        self._limit: int | None = None
        self._select: list[str] | None = None

    def _clone(self) -> "FakeQuery":
        q = FakeQuery(self._db, self._collection)
        q._filters, q._order, q._limit, q._select = list(self._filters), list(self._order), self._limit, self._select
        return q

    def where(self, *, filter: Any) -> "FakeQuery":  # noqa: A002 - mirrors the SDK's keyword
        op, value = filter.op_string, filter.value
        if op in ("in", "not-in", "array-contains-any"):
            if not isinstance(value, list) or not value:
                raise FirestoreLimitError(f"'{op}' needs a non-empty list")
            if len(value) > 30:
                raise FirestoreLimitError(f"'{op}' supports at most 30 values (got {len(value)})")
        q = self._clone()
        q._filters.append((filter.field_path, op, value))
        return q

    def order_by(self, field: str, direction: str = "ASCENDING") -> "FakeQuery":
        q = self._clone()
        q._order.append((field, direction))
        return q

    def limit(self, n: int) -> "FakeQuery":
        q = self._clone()
        q._limit = n
        return q

    def select(self, fields: list[str]) -> "FakeQuery":
        q = self._clone()
        q._select = list(fields)
        return q

    @staticmethod
    def _match(doc: dict, field: str, op: str, value: Any) -> bool:
        if field not in doc:
            return False
        v = doc[field]
        if op == "==":
            return v == value
        if op == "in":
            return v in value
        if op in ("array_contains", "array-contains"):  # Python SDK spelling / web SDK spelling
            return isinstance(v, list) and value in v
        if v is None:
            return False
        return {">=": v >= value, "<=": v <= value, ">": v > value, "<": v < value}[op]

    async def stream(self):
        self._db.reads[self._collection] += 1
        rows = [(i, d) for i, d in self._db._store.get(self._collection, {}).items()
                if all(self._match(d, f, op, v) for f, op, v in self._filters)]
        for field, direction in reversed(self._order):
            rows = [r for r in rows if field in r[1]]
            rows.sort(key=lambda r: r[1][field], reverse=direction == "DESCENDING")
        if self._limit is not None:
            rows = rows[: self._limit]
        for doc_id, data in rows:
            out = {k: v for k, v in data.items() if self._select is None or k in self._select}
            yield FakeSnapshot(FakeDocRef(self._db, self._collection, doc_id), copy.deepcopy(out))


class FakeCollection(FakeQuery):
    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._db, self._collection, doc_id)


class FakeBatch:
    def __init__(self, db: "FakeFirestore") -> None:
        self._db, self._ops = db, []

    def set(self, ref: FakeDocRef, data: dict) -> None:
        _validate(data, ref.id)  # the real client fails at encode time too
        self._ops.append(("set", ref, copy.deepcopy(data)))

    def update(self, ref: FakeDocRef, fields: dict) -> None:
        self._ops.append(("update", ref, copy.deepcopy(fields)))

    def delete(self, ref: FakeDocRef) -> None:
        self._ops.append(("delete", ref, None))

    async def commit(self) -> None:
        if len(self._ops) > 500:
            raise FirestoreLimitError(f"a batch can hold at most 500 writes (got {len(self._ops)})")
        for op, ref, data in self._ops:
            if op == "delete":
                self._db._store.get(ref.collection, {}).pop(ref.id, None)
                self._db.writes[ref.collection] += 1
            else:
                self._db._write(ref, data) if op == "set" else self._db._update(ref, data)
        self.commits = getattr(self, "commits", 0) + 1


class FakeTxn:
    def __init__(self) -> None:
        self.writes: list[tuple[FakeDocRef, dict]] = []

    async def get(self, ref: FakeDocRef) -> FakeSnapshot:
        return await ref.get()

    def set(self, ref: FakeDocRef, data: dict) -> None:
        _validate(data, ref.id)
        self.writes.append((ref, copy.deepcopy(data)))


class FakeFirestore:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict]] = {}
        self.writes: Counter[str] = Counter()
        self.reads: Counter[str] = Counter()

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)

    def batch(self) -> FakeBatch:
        return FakeBatch(self)

    async def get_all(self, refs: list[FakeDocRef]):
        for ref in refs:
            yield await ref.get()

    async def run_transaction(self, fn):
        """Transaction seam for FirestoreRepository: reads go straight through, writes apply on success."""
        txn = FakeTxn()
        result = await fn(txn)
        for ref, data in txn.writes:
            self._write(ref, data)
        return result

    # ---- storage
    def _write(self, ref: FakeDocRef, data: dict) -> None:
        if _validate(data, ref.id) > MAX_DOC_BYTES:
            raise FirestoreLimitError(f"{ref.collection}/{ref.id}: document exceeds 1 MiB")
        self._store.setdefault(ref.collection, {})[ref.id] = copy.deepcopy(data)
        self.writes[ref.collection] += 1

    def _update(self, ref: FakeDocRef, fields: dict) -> None:
        cur = self._store.get(ref.collection, {}).get(ref.id)
        if cur is None:
            raise FirestoreLimitError(f"update on missing document {ref.collection}/{ref.id}")
        merged = {**cur, **copy.deepcopy(fields)}
        self._write(ref, merged)

    # ---- test helpers
    def doc(self, collection: str, doc_id: str) -> dict | None:
        return copy.deepcopy(self._store.get(collection, {}).get(doc_id))

    def docs(self, collection: str) -> dict[str, dict]:
        return copy.deepcopy(self._store.get(collection, {}))
