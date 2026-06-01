"""Service-backed stores: no silent fallback (round-5 WS11)."""

from __future__ import annotations

import pytest

from acp.context.vector_store import PgVectorStore


def test_pgvector_require_real_refuses_silent_fallback() -> None:
    # explicitly requiring a real service must raise, not degrade to memory
    with pytest.raises(RuntimeError, match="silently fall back"):
        PgVectorStore(dsn=None, require_real=True)


def test_pgvector_reports_memory_fallback_when_not_required() -> None:
    store = PgVectorStore(dsn=None)
    # backend is explicit + visible (never silently claims to be pgvector)
    assert store.backend == "memory-fallback"


@pytest.mark.live_pgvector
def test_pgvector_live_contract() -> None:
    import os
    dsn = os.environ.get("ACP_PGVECTOR_DSN")
    if not dsn or not PgVectorStore.available():
        pytest.skip("no live pgvector (ACP_PGVECTOR_DSN + psycopg + pgvector)")
    store = PgVectorStore(dsn=dsn, require_real=True)
    assert store.backend == "pgvector"


@pytest.mark.live_qdrant
def test_qdrant_is_real_engine_not_memory_fallback() -> None:
    from acp.context.vector_store import QdrantStore
    if not QdrantStore.available():
        pytest.skip("qdrant-client not installed")
    store = QdrantStore(location=":memory:")
    # a real qdrant engine, explicitly NOT a memory-fallback buffer
    assert store.backend == "qdrant"
