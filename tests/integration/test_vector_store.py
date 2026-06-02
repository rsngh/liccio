"""VectorStore + embedders (round-1 two-day D2B3)."""

from __future__ import annotations

import os

import pytest

from acp.context.compiler import ContextCompiler
from acp.context.embeddings import CachingEmbedder, HashingEmbedder, OpenAIEmbedder
from acp.context.vector_store import (
    InMemoryVectorStore,
    PgVectorStore,
    QdrantStore,
    VectorRecord,
)
from acp.schemas.task import Task


def test_inmemory_vector_store_roundtrip() -> None:
    store = InMemoryVectorStore()
    store.upsert([
        VectorRecord(id="a", vector=[1.0, 0.0], snapshot_id="s", payload={"p": "a"}),
        VectorRecord(id="b", vector=[0.0, 1.0], snapshot_id="s", payload={"p": "b"}),
    ])
    hits = store.query([1.0, 0.1], top_k=2, snapshot_id="s")
    assert hits[0].id == "a"
    assert store.delete_snapshot("s") == 2
    assert store.query([1.0, 0.0], top_k=2) == []


def test_embedding_cache_reuses_content_hash() -> None:
    emb = CachingEmbedder(HashingEmbedder(dim=64))
    v1 = emb.embed("hello world")
    v2 = emb.embed("hello world")
    assert v1 == v2
    assert emb.hits == 1 and emb.misses == 1


def test_pgvector_and_qdrant_unavailable_graceful() -> None:
    # Without the optional deps/services, availability is False but the store
    # still functions (in-memory fallback) so callers stay correct.
    assert isinstance(PgVectorStore.available(), bool)
    assert isinstance(QdrantStore.available(), bool)
    pg = PgVectorStore()
    pg.upsert([VectorRecord(id="x", vector=[1.0], snapshot_id="s")])
    assert pg.query([1.0], top_k=1, snapshot_id="s")[0].id == "x"


def test_context_compiler_can_use_vector_store(tmp_path) -> None:
    (tmp_path / "calculator.py").write_text("def divide(a, b):\n    return a / b\n")
    (tmp_path / "other.py").write_text("def greet():\n    return 'hi'\n")
    store = InMemoryVectorStore()
    task = Task(repo_id="r", title="Fix divide", body="divide by zero")
    pack = ContextCompiler(tmp_path, "r", "snap", vector_store=store).compile(
        task, token_budget=20_000
    )
    assert pack.items
    # vectors were upserted into the store
    assert store.query(store._records[next(iter(store._records))].vector, top_k=1)


def test_factory_defaults_to_hashing_and_memory() -> None:
    from acp.context.factory import make_embedder, make_vector_store
    from acp.core.config import ACPSettings

    settings = ACPSettings()  # no key, no vector backend enabled
    ec = make_embedder(settings)
    assert ec.backend == "hashing"
    assert len(ec.embedder.embed("hello")) == 256
    vc = make_vector_store(settings)
    assert vc.backend == "memory"
    assert isinstance(vc.store, InMemoryVectorStore)


def test_factory_respects_forced_hashing_env(monkeypatch) -> None:
    from acp.context.factory import make_embedder
    from acp.core.config import ACPSettings

    monkeypatch.setenv("ACP_EMBEDDER", "hashing")
    ec = make_embedder(ACPSettings(openai_api_key="sk-test"))
    assert ec.backend == "hashing"
    assert "forced" in ec.reason


def test_factory_openai_requested_but_unavailable_degrades(monkeypatch) -> None:
    from acp.context.factory import make_embedder
    from acp.core.config import ACPSettings

    monkeypatch.setenv("ACP_EMBEDDER", "openai")
    # No real key/SDK wired here -> graceful degrade to hashing, never raises.
    ec = make_embedder(ACPSettings())
    assert ec.backend in ("openai", "hashing")


def test_factory_pgvector_enabled_without_dsn_uses_memory(monkeypatch) -> None:
    from acp.context.factory import make_vector_store
    from acp.core.config import ACPSettings

    monkeypatch.delenv("ACP_PGVECTOR_DSN", raising=False)
    vc = make_vector_store(ACPSettings(enable_pgvector=True))
    assert vc.backend == "memory"


def test_compiler_auto_selects_backend_and_records_notes(tmp_path) -> None:
    from acp.core.config import ACPSettings

    (tmp_path / "calculator.py").write_text("def divide(a, b):\n    return a / b\n")
    task = Task(repo_id="r", title="Fix divide", body="divide by zero")
    compiler = ContextCompiler(tmp_path, "r", "snap", settings=ACPSettings())
    assert compiler.embedder is not None
    pack = compiler.compile(task, token_budget=20_000)
    notes = " ".join(pack.retrieval_trace.notes)
    assert "embedder=hashing" in notes
    assert "vector_store=memory" in notes


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"), reason="no OPENAI_API_KEY for live embedding"
)
def test_openai_embedder_live() -> None:
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    from acp.core.config import reset_settings

    reset_settings()
    emb = OpenAIEmbedder()
    if not emb.available:
        pytest.skip("openai SDK not installed")
    v = emb.embed("agent control plane retrieval test")
    assert len(v) >= 256
    assert emb.dim == len(v)
