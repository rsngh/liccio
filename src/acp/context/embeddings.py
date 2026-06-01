"""Embedding abstraction (charter §10).

Default is a deterministic hashing embedder (no heavy deps, reproducible). A real
sentence-transformers backend can be plugged in via the same protocol when the
optional dependency is installed.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Deterministic bag-of-tokens hashing embedding (cosine-comparable)."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)  # noqa: S324 - non-crypto
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class OpenAIEmbedder:
    """Optional OpenAI embeddings (round-1 two-day D2B3).

    Lazy-imports ``openai`` and requires a key. ``available`` is False otherwise,
    letting callers fall back to the hashing embedder.
    """

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536) -> None:
        self.model = model
        self.dim = dim

    def _client(self):
        from acp.core.config import get_settings
        from acp.core.optional import try_import

        openai = try_import("openai")
        if openai is None:
            return None
        key = get_settings().openai_api_key
        if key is None:
            return None
        return openai.OpenAI(api_key=key.get_secret_value())

    @property
    def available(self) -> bool:
        return self._client() is not None

    def embed(self, text: str) -> list[float]:
        client = self._client()
        if client is None:
            raise RuntimeError("OpenAI embedder unavailable (SDK or key missing)")
        resp = client.embeddings.create(model=self.model, input=text[:8000])
        vec = list(resp.data[0].embedding)
        self.dim = len(vec)
        return vec


class SentenceTransformerEmbedder:
    """Optional local sentence-transformers embedder."""

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model
        self._model = None
        self.dim = 384

    def _ensure(self):
        if self._model is None:
            from acp.core.optional import try_import

            st = try_import("sentence_transformers")
            if st is None:
                return None
            self._model = st.SentenceTransformer(self.model_name)
        return self._model

    @property
    def available(self) -> bool:
        return self._ensure() is not None

    def embed(self, text: str) -> list[float]:
        model = self._ensure()
        if model is None:
            raise RuntimeError("sentence-transformers unavailable")
        vec = model.encode(text).tolist()
        self.dim = len(vec)
        return vec


class CachingEmbedder:
    """Wraps an embedder with a cache keyed by (model, content_hash, dim)."""

    def __init__(self, inner: Embedder, model_name: str = "") -> None:
        self.inner = inner
        self.dim = inner.dim
        self.model_name = model_name or type(inner).__name__
        self._cache: dict[str, list[float]] = {}
        self.hits = 0
        self.misses = 0

    def _key(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.model_name}:{self.dim}:{h}"

    def embed(self, text: str) -> list[float]:
        key = self._key(text)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        vec = self.inner.embed(text)
        self.dim = self.inner.dim
        self._cache[key] = vec
        return vec
