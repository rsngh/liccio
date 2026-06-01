"""Real vector-DB contract tests (round-2 Block H).

Qdrant runs against a real local engine (qdrant-client ':memory:' is a genuine
Qdrant engine, not our InMemory fallback). pgvector requires a live Postgres and
is skipped unless ACP_PGVECTOR_DSN is set.
"""

from __future__ import annotations

import os

import pytest

from acp.context.vector_store import QdrantStore, VectorRecord

QDRANT = QdrantStore.available()


@pytest.mark.live_qdrant
@pytest.mark.skipif(not QDRANT, reason="qdrant-client not installed")
def test_qdrant_contract() -> None:
    store = QdrantStore(location=":memory:", dim=4)
    assert store.backend == "qdrant"  # real engine, not a fallback
    store.upsert([
        VectorRecord(id="a", vector=[1.0, 0.0, 0.0, 0.0], snapshot_id="s1", payload={"path": "a"}),
        VectorRecord(id="b", vector=[0.0, 1.0, 0.0, 0.0], snapshot_id="s1", payload={"path": "b"}),
        VectorRecord(id="c", vector=[1.0, 0.0, 0.0, 0.0], snapshot_id="s2", payload={"path": "c"}),
    ])
    # nearest to 'a' direction
    hits = store.query([1.0, 0.05, 0.0, 0.0], top_k=2, snapshot_id="s1")
    assert hits and hits[0].id == "a"
    # filter by snapshot
    assert all(h.payload["snapshot_id"] == "s1" for h in hits)
    s2 = store.query([1.0, 0.0, 0.0, 0.0], top_k=5, snapshot_id="s2")
    assert {h.id for h in s2} == {"c"}
    # delete snapshot
    store.delete_snapshot("s1")
    assert store.query([1.0, 0.0, 0.0, 0.0], top_k=5, snapshot_id="s1") == []
    # s2 persists
    assert store.query([1.0, 0.0, 0.0, 0.0], top_k=5, snapshot_id="s2")


@pytest.mark.live_pgvector
@pytest.mark.skipif(not os.environ.get("ACP_PGVECTOR_DSN"), reason="no ACP_PGVECTOR_DSN")
def test_pgvector_contract() -> None:
    from acp.context.vector_store import PgVectorStore

    store = PgVectorStore(dsn=os.environ["ACP_PGVECTOR_DSN"])
    assert store.backend == "pgvector"  # must be service-backed, not fallback
    store.upsert([VectorRecord(id="a", vector=[1.0, 0.0], snapshot_id="s")])
    assert store.query([1.0, 0.0], top_k=1, snapshot_id="s")[0].id == "a"
