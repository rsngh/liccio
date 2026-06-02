"""Config-driven embedder / vector-store selection (round-1 two-day D2B3).

Picks the best available backend from settings and degrades gracefully:
  * embedder: OpenAI (if SDK + key) -> sentence-transformers (if SDK) -> hashing
  * vector store: pgvector (if enabled + DSN + deps) -> qdrant (if enabled + deps)
    -> in-memory

Selection never raises for a missing optional dependency: an unavailable
backend is skipped and the next candidate is tried, ending at the always-present
default. Each call returns the concrete instance plus a short reason string so
the compiler/trace can record which backend was chosen and why.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from acp.context.embeddings import (
    CachingEmbedder,
    Embedder,
    HashingEmbedder,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
)
from acp.context.vector_store import (
    InMemoryVectorStore,
    PgVectorStore,
    QdrantStore,
    VectorStore,
)
from acp.core.config import ACPSettings, get_settings


@dataclass
class EmbedderChoice:
    embedder: Embedder
    backend: str
    reason: str


@dataclass
class VectorStoreChoice:
    store: VectorStore
    backend: str
    reason: str


def make_embedder(
    settings: ACPSettings | None = None, *, dim: int = 256, cache: bool = True
) -> EmbedderChoice:
    """Select the best available embedder from settings.

    ``ACP_EMBEDDER`` env var ("openai"|"sentence_transformers"|"hashing") forces a
    preference; absent that, OpenAI is preferred when a key is configured.
    """
    settings = settings or get_settings()
    pref = os.environ.get("ACP_EMBEDDER", "").strip().lower()

    def _wrap(inner: Embedder, backend: str, reason: str) -> EmbedderChoice:
        chosen = CachingEmbedder(inner) if cache else inner
        return EmbedderChoice(embedder=chosen, backend=backend, reason=reason)

    # Explicit hashing request short-circuits.
    if pref == "hashing":
        return _wrap(HashingEmbedder(dim=dim), "hashing", "forced via ACP_EMBEDDER")

    want_openai = pref == "openai" or (pref == "" and settings.openai_api_key is not None)
    if want_openai:
        oa = OpenAIEmbedder()
        if oa.available:
            return _wrap(oa, "openai", "openai SDK + key available")
        if pref == "openai":
            return _wrap(HashingEmbedder(dim=dim), "hashing",
                         "openai requested but SDK/key unavailable")

    if pref == "sentence_transformers" or pref == "":
        st = SentenceTransformerEmbedder()
        if st.available:
            return _wrap(st, "sentence_transformers", "sentence-transformers available")
        if pref == "sentence_transformers":
            return _wrap(HashingEmbedder(dim=dim), "hashing",
                         "sentence-transformers requested but unavailable")

    return _wrap(HashingEmbedder(dim=dim), "hashing", "default (no optional backend)")


def make_vector_store(
    settings: ACPSettings | None = None, *, dim: int = 256
) -> VectorStoreChoice:
    """Select a vector store from settings, degrading to in-memory."""
    settings = settings or get_settings()

    if settings.enable_pgvector:
        dsn = os.environ.get("ACP_PGVECTOR_DSN")
        if dsn and PgVectorStore.available():
            return VectorStoreChoice(PgVectorStore(dsn=dsn), "pgvector",
                                     "pgvector enabled + DSN + deps available")
        return VectorStoreChoice(InMemoryVectorStore(), "memory",
                                 "pgvector enabled but DSN/deps unavailable")

    if settings.enable_qdrant:
        if QdrantStore.available():
            loc = os.environ.get("ACP_QDRANT_LOCATION", ":memory:")
            return VectorStoreChoice(QdrantStore(location=loc, dim=dim), "qdrant",
                                     "qdrant enabled + client available")
        return VectorStoreChoice(InMemoryVectorStore(), "memory",
                                 "qdrant enabled but client unavailable")

    return VectorStoreChoice(InMemoryVectorStore(), "memory", "default in-memory store")
