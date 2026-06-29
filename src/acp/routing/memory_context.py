"""Embedding-kNN routing memory (ACRouter-style; additive, non-breaking).

Accumulates *verified* per-task routing OUTCOMES — which action was taken, the reward it earned, its
cost — keyed by an embedding of the task, and retrieves the k most-similar past tasks to enrich the
routing context with per-action neighbour evidence.

Motivation (Agent-as-a-Router, 2606.22902): the routing bottleneck is an *information deficit*, not
reasoning. Coarse categorical context (liccio's ``task_type|risk_level``) captures only part of the
per-task signal; the rest lives in the task content, which embedding-kNN over an outcome memory
recovers. This is the per-task-retrieval form of the cluster-context idea — chosen over k-means
because it slots onto the existing bandit as a cold-start prior and warm-starts from logged rewards.

NON-BREAKING: importing or constructing this changes nothing. It affects routing only when a
``MemoryContext`` is passed to ``RoutingFeatureExtractor.extract(..., memory=...)`` (which adds
``neighbor_*`` feature keys) and, in turn, ``SimulatedBanditPolicy`` uses those keys *only* to seed
COLD arms (n==0). With no memory wired in, every path is unchanged. The default embedder is the
deterministic, dependency-free ``HashingEmbedder``; a real code embedder (voyage / sentence-
transformers / OpenAI) plugs in via the same ``Embedder`` protocol.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from acp.context.embeddings import Embedder, HashingEmbedder, cosine


@dataclass
class _Entry:
    vec: list[float]
    action_key: str
    reward: float
    cost: float


@dataclass
class NeighborContext:
    """Aggregated evidence from the k nearest past tasks (>= similarity threshold)."""

    n: int                                          # neighbours retained
    action_reward: dict[str, float]                 # action_key -> mean reward over neighbours
    action_n: dict[str, int]                        # action_key -> how many neighbours used it
    best_action: str | None                         # highest mean-reward action among neighbours

    @property
    def sparse(self) -> bool:
        """True when no neighbour cleared the threshold -> caller falls back to coarse context."""
        return self.n == 0


@dataclass
class MemoryContext:
    """Online, FIFO-bounded embedding store of routing outcomes with cosine-kNN retrieval."""

    embedder: Embedder = field(default_factory=HashingEmbedder)
    k: int = 10
    threshold: float = 0.5
    maxlen: int = 20_000
    _store: deque = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        # rebind the deque with the configured bound (a field default can't see maxlen)
        self._store = deque(self._store, maxlen=self.maxlen)

    def __len__(self) -> int:
        return len(self._store)

    def add(self, task_text: str, action_key: str, reward: float, cost: float = 0.0) -> None:
        """Record a verified outcome: the action taken on ``task_text`` and what it earned/cost."""
        self._store.append(
            _Entry(self.embedder.embed(task_text), action_key, float(reward), float(cost)))

    def query(self, task_text: str, *, k: int | None = None,
              threshold: float | None = None) -> NeighborContext:
        """Per-action evidence from the nearest past tasks to ``task_text`` (cosine kNN)."""
        k = self.k if k is None else k
        threshold = self.threshold if threshold is None else threshold
        if not self._store:
            return NeighborContext(0, {}, {}, None)
        v = self.embedder.embed(task_text)
        ranked = sorted(
            ((cosine(v, e.vec), e) for e in self._store), key=lambda t: t[0], reverse=True)[:k]
        nbrs = [e for sim, e in ranked if sim >= threshold]
        if not nbrs:
            return NeighborContext(0, {}, {}, None)
        rewards: dict[str, list[float]] = {}
        for e in nbrs:
            rewards.setdefault(e.action_key, []).append(e.reward)
        action_reward = {a: sum(rs) / len(rs) for a, rs in rewards.items()}
        action_n = {a: len(rs) for a, rs in rewards.items()}
        best = max(action_reward, key=lambda a: action_reward[a]) if action_reward else None
        return NeighborContext(len(nbrs), action_reward, action_n, best)
