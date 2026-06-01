"""Hybrid retrieval and scoring (charter §10.3).

Combines keyword (BM25 when available, else token-overlap), vector similarity
(via an Embedder), and several boosts. Weights are configurable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.context.embeddings import Embedder, HashingEmbedder, cosine
from acp.schemas.context import ContextItem, RetrievalTrace

DEFAULT_WEIGHTS: dict[str, float] = {
    "keyword": 0.35,
    "vector": 0.35,
    "path": 0.10,
    "symbol": 0.10,
    "test": 0.05,
    "prior_run": 0.05,
}

STRATEGIES = (
    "keyword_only",
    "embedding_only",
    "hybrid_keyword_embedding",
    "symbol_graph",
    "test_focused",
    "bug_reproduction",
    "architecture",
    "recent_changes",
    "prior_failures",
    "minimal",
    "max_context",
)


def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


@dataclass
class ScoredItem:
    item: ContextItem
    score: float
    components: dict[str, float] = field(default_factory=dict)


class HybridRetriever:
    def __init__(
        self,
        items: list[ContextItem],
        embedder: Embedder | None = None,
        weights: dict[str, float] | None = None,
        prior_paths: set[str] | None = None,
    ) -> None:
        self.items = items
        self.embedder = embedder or HashingEmbedder()
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.prior_paths = prior_paths or set()
        self._doc_vecs: list[list[float]] = []
        self._bm25 = None
        self._prepare()

    def _prepare(self) -> None:
        self._doc_vecs = [self.embedder.embed(it.content) for it in self.items]
        try:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi([_tokenize(it.content) for it in self.items])
        except Exception:  # noqa: BLE001 - optional dep
            self._bm25 = None

    def _keyword_scores(self, query: str) -> list[float]:
        q = _tokenize(query)
        if not q:
            return [0.0] * len(self.items)
        if self._bm25 is not None:
            raw = list(self._bm25.get_scores(q))
            top = max(raw) or 1.0
            return [r / top for r in raw]
        # fallback: normalized token-overlap
        qset = set(q)
        scores = []
        for it in self.items:
            toks = set(_tokenize(it.content))
            scores.append(len(qset & toks) / (len(qset) or 1))
        return scores

    def _vector_scores(self, query: str) -> list[float]:
        qv = self.embedder.embed(query)
        return [max(0.0, cosine(qv, dv)) for dv in self._doc_vecs]

    def retrieve(
        self,
        query: str,
        strategy: str = "hybrid_keyword_embedding",
        top_k: int = 50,
    ) -> tuple[list[ScoredItem], RetrievalTrace]:
        kw = self._keyword_scores(query)
        vec = self._vector_scores(query)
        w = dict(self.weights)
        if strategy == "keyword_only":
            w = {**w, "vector": 0.0}
        elif strategy == "embedding_only":
            w = {**w, "keyword": 0.0}

        scored: list[ScoredItem] = []
        qtoks = set(_tokenize(query))
        for i, it in enumerate(self.items):
            path_boost = 1.0 if qtoks & set(_tokenize(it.path)) else 0.0
            symbol_boost = 1.0 if (it.symbol_name and it.symbol_name.lower() in qtoks) else 0.0
            test_boost = 1.0 if it.kind == "test_chunk" else 0.0
            prior_boost = 1.0 if it.path in self.prior_paths else 0.0
            if strategy == "test_focused":
                test_boost *= 3.0
            if strategy == "prior_failures":
                prior_boost *= 3.0
            if strategy == "symbol_graph":
                symbol_boost *= 2.0
            comps = {
                "keyword": w["keyword"] * kw[i],
                "vector": w["vector"] * vec[i],
                "path": w["path"] * path_boost,
                "symbol": w["symbol"] * symbol_boost,
                "test": w["test"] * test_boost,
                "prior_run": w["prior_run"] * prior_boost,
            }
            total = sum(comps.values())
            it.score = total
            scored.append(ScoredItem(item=it, score=total, components=comps))

        scored.sort(key=lambda s: s.score, reverse=True)
        selected = scored[:top_k]
        trace = RetrievalTrace(
            strategy=strategy,
            query_terms=sorted(qtoks),
            weights=w,
            considered=len(self.items),
            selected=len(selected),
            dropped=len(self.items) - len(selected),
            notes=[f"bm25={'on' if self._bm25 else 'fallback'}"],
        )
        return selected, trace
