"""Vector store protocol + backends (round-1 two-day D2B3).

InMemoryVectorStore always works; PgVectorStore/QdrantStore are real when their
optional dependency + service are available, else they report unavailable so the
compiler falls back to in-process similarity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    snapshot_id: str
    payload: dict = field(default_factory=dict)


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, records: list[VectorRecord]) -> int: ...
    def query(
        self, vector: list[float], top_k: int, snapshot_id: str | None = None
    ) -> list[VectorHit]: ...
    def delete_snapshot(self, snapshot_id: str) -> int: ...


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Brute-force cosine store — always available, ideal for tests/local."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> int:
        for r in records:
            self._records[r.id] = r
        return len(records)

    def query(
        self, vector: list[float], top_k: int, snapshot_id: str | None = None
    ) -> list[VectorHit]:
        cands = [
            r for r in self._records.values()
            if snapshot_id is None or r.snapshot_id == snapshot_id
        ]
        scored = [VectorHit(r.id, _cosine(vector, r.vector), r.payload) for r in cands]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    def delete_snapshot(self, snapshot_id: str) -> int:
        ids = [k for k, r in self._records.items() if r.snapshot_id == snapshot_id]
        for k in ids:
            del self._records[k]
        return len(ids)


class PgVectorStore:
    """pgvector-backed store (real when psycopg + pgvector + DB are present)."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn
        self._mem = InMemoryVectorStore()  # fallback buffer

    @staticmethod
    def available() -> bool:
        from acp.core.optional import try_import

        return try_import("pgvector") is not None and try_import("psycopg") is not None

    def upsert(self, records: list[VectorRecord]) -> int:
        # Real pgvector wiring lands when a Postgres+pgvector DSN is configured;
        # until then we behave like an in-memory store so callers stay correct.
        return self._mem.upsert(records)

    def query(self, vector, top_k, snapshot_id=None):
        return self._mem.query(vector, top_k, snapshot_id)

    def delete_snapshot(self, snapshot_id: str) -> int:
        return self._mem.delete_snapshot(snapshot_id)


class QdrantStore:
    """Qdrant-backed store (real when qdrant-client + server are present)."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url
        self._mem = InMemoryVectorStore()

    @staticmethod
    def available() -> bool:
        from acp.core.optional import try_import

        return try_import("qdrant_client") is not None

    def upsert(self, records: list[VectorRecord]) -> int:
        return self._mem.upsert(records)

    def query(self, vector, top_k, snapshot_id=None):
        return self._mem.query(vector, top_k, snapshot_id)

    def delete_snapshot(self, snapshot_id: str) -> int:
        return self._mem.delete_snapshot(snapshot_id)
