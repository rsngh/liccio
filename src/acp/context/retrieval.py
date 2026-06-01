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

# Strategy-specific chunk-kind preferences (multiplier into the "kind" boost).
STRATEGY_KIND_PREFS: dict[str, dict[str, float]] = {
    "bug_reproduction": {"test_chunk": 3.0, "symbol_chunk": 2.0},
    "architecture": {"doc_chunk": 3.0, "manifest_chunk": 2.0, "instruction_chunk": 2.0},
    "recent_changes": {"recent_commit_chunk": 3.0, "symbol_chunk": 1.0},
    "prior_failures": {"prior_run_summary_chunk": 3.0, "test_chunk": 1.0},
    "test_focused": {"test_chunk": 3.0},
    "max_context": {"file_chunk": 1.0, "doc_chunk": 1.0, "manifest_chunk": 1.0},
}

# Strategy-specific item budgets.
STRATEGY_TOP_K: dict[str, int] = {
    "minimal": 8,
    "max_context": 200,
}


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
        vector_store=None,
        snapshot_id: str = "snap",
    ) -> None:
        self.items = items
        self.embedder = embedder or HashingEmbedder()
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.prior_paths = prior_paths or set()
        self.vector_store = vector_store
        self.snapshot_id = snapshot_id
        self._doc_vecs: list[list[float]] = []
        self._bm25 = None
        self._prepare()

    def _prepare(self) -> None:
        self._doc_vecs = [self.embedder.embed(it.content) for it in self.items]
        if self.vector_store is not None:
            from acp.context.vector_store import VectorRecord

            self.vector_store.upsert([
                VectorRecord(id=it.id, vector=self._doc_vecs[i],
                             snapshot_id=self.snapshot_id, payload={"path": it.path})
                for i, it in enumerate(self.items)
            ])
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
        if self.vector_store is not None:
            hits = self.vector_store.query(qv, top_k=len(self.items),
                                           snapshot_id=self.snapshot_id)
            by_id = {h.id: max(0.0, h.score) for h in hits}
            return [by_id.get(it.id, 0.0) for it in self.items]
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

        # Per-strategy preferred chunk kinds (round-1 §5: real differentiation).
        kind_pref = STRATEGY_KIND_PREFS.get(strategy, {})
        effective_top_k = STRATEGY_TOP_K.get(strategy, top_k)

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
                "kind": 0.15 * kind_pref.get(it.kind, 0.0),
            }
            total = sum(comps.values())
            it.score = total
            scored.append(ScoredItem(item=it, score=total, components=comps))

        scored.sort(key=lambda s: s.score, reverse=True)
        selected = scored[:effective_top_k]
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
