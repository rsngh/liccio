"""Vector store protocol + backends (round-1 two-day D2B3).

InMemoryVectorStore always works; PgVectorStore/QdrantStore are real when their
optional dependency + service are available, else they report unavailable so the
compiler falls back to in-process similarity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


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
        self.backend = "memory"
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
    """pgvector-backed store (real when psycopg + pgvector + DB are present).

    With a live DSN it issues real SQL against a ``acp_vectors`` table using the
    ``<=>`` cosine-distance operator; without one it transparently buffers in
    memory so callers stay correct in dev/test.
    """

    def __init__(
        self,
        dsn: str | None = None,
        *,
        require_real: bool = False,
        dim: int = 256,
        table: str = "acp_vectors",
    ) -> None:
        self.dsn = dsn
        self.dim = dim
        self.table = table
        # No silent fallback (round-5 WS11): if the caller explicitly requires a
        # real service-backed store, refuse to degrade to memory.
        if require_real and not (dsn and self.available()):
            raise RuntimeError(
                "pgvector requested (require_real=True) but unavailable: need a DSN "
                "+ psycopg + pgvector. Refusing to silently fall back to memory.")
        self._mem = InMemoryVectorStore()  # fallback buffer
        self._conn: Any = None
        self.backend = "pgvector" if (dsn and self.available()) else "memory-fallback"
        if self.backend == "pgvector":
            self._connect()

    @staticmethod
    def available() -> bool:
        from acp.core.optional import try_import

        return try_import("pgvector") is not None and try_import("psycopg") is not None

    # ---- real pgvector wiring -------------------------------------------
    def _connect(self) -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        assert self.dsn is not None  # guaranteed: backend=="pgvector" implies a DSN
        self._conn = psycopg.connect(self.dsn, autocommit=True)
        register_vector(self._conn)
        self._conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table} ("  # noqa: S608 - table is internal
            "id text PRIMARY KEY, snapshot_id text, "
            f"embedding vector({self.dim}), payload jsonb)"
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS {self.table}_snap_idx "  # noqa: S608
            f"ON {self.table} (snapshot_id)"
        )

    def upsert(self, records: list[VectorRecord]) -> int:
        if self._conn is None:
            return self._mem.upsert(records)
        import json

        with self._conn.cursor() as cur:
            for r in records:
                cur.execute(
                    f"INSERT INTO {self.table} (id, snapshot_id, embedding, payload) "  # noqa: S608
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
                    "snapshot_id = EXCLUDED.snapshot_id, embedding = EXCLUDED.embedding, "
                    "payload = EXCLUDED.payload",
                    (r.id, r.snapshot_id, r.vector, json.dumps(r.payload)),
                )
        return len(records)

    def query(self, vector, top_k, snapshot_id=None):
        if self._conn is None:
            return self._mem.query(vector, top_k, snapshot_id)
        where = "" if snapshot_id is None else "WHERE snapshot_id = %(snap)s"
        sql = (
            f"SELECT id, payload, 1 - (embedding <=> %(vec)s) AS score "  # noqa: S608
            f"FROM {self.table} {where} ORDER BY embedding <=> %(vec)s LIMIT %(k)s"
        )
        params = {"vec": vector, "k": top_k, "snap": snapshot_id}
        rows = self._conn.execute(sql, params).fetchall()
        return [VectorHit(rid, float(score), payload or {}) for rid, payload, score in rows]

    def delete_snapshot(self, snapshot_id: str) -> int:
        if self._conn is None:
            return self._mem.delete_snapshot(snapshot_id)
        cur = self._conn.execute(
            f"DELETE FROM {self.table} WHERE snapshot_id = %s",  # noqa: S608
            (snapshot_id,),
        )
        return cur.rowcount


class QdrantStore:
    """Qdrant-backed store — a real Qdrant engine (server URL or local ':memory:'
    / file path), NOT an in-memory fallback. Requires qdrant-client."""

    def __init__(self, location: str = ":memory:", collection: str = "acp_chunks",
                 dim: int = 256) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.backend = "qdrant"
        self.collection = collection
        self.dim = dim
        self.client = QdrantClient(location=location)
        if not self.client.collection_exists(collection):
            self.client.create_collection(
                collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    @staticmethod
    def available() -> bool:
        from acp.core.optional import try_import

        return try_import("qdrant_client") is not None

    def upsert(self, records: list[VectorRecord]) -> int:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=abs(hash(r.id)) % (10**18), vector=r.vector,
                        payload={"rid": r.id, "snapshot_id": r.snapshot_id, **r.payload})
            for r in records
        ]
        self.client.upsert(self.collection, points=points)
        return len(records)

    def query(self, vector, top_k, snapshot_id=None):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        flt = None
        if snapshot_id is not None:
            flt = Filter(must=[FieldCondition(key="snapshot_id",
                                              match=MatchValue(value=snapshot_id))])
        hits = self.client.query_points(
            self.collection, query=vector, limit=top_k, query_filter=flt
        ).points
        return [VectorHit(h.payload["rid"], float(h.score), h.payload) for h in hits]

    def delete_snapshot(self, snapshot_id: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        flt = Filter(must=[FieldCondition(key="snapshot_id",
                                          match=MatchValue(value=snapshot_id))])
        self.client.delete(self.collection, points_selector=FilterSelector(filter=flt))
        return 1
