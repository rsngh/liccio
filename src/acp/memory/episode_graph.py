"""Episode graph + procedural recipe memory (GOALS P4).

The experience bank already stores episodes (with aging, tenant isolation, poison quarantine)
and each episode carries a ``recipe`` — the winning lever SEQUENCE. What was missing for
production-grade memory is two things the bank doesn't do:

  * an EPISODE GRAPH linking episodes that share a failure signature, changed symbols, repo
    family, or task type — so a NEW issue can borrow the procedure that solved a RELATED issue
    (transfer across an issue sequence, not just exact-signature recall);
  * PROCEDURAL recipe retrieval: given a failure signature, return the best known-good lever
    sequence to replay — directly if we've solved this signature, otherwise transferred from the
    closest related signature in the graph.

Pure and dependency-free (plain adjacency dicts, deterministic ordering), matching the rest of
the memory subsystem. Operates on :class:`experience_bank.ExperienceEpisode` lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.memory.experience_bank import ExperienceEpisode

# how much each shared attribute contributes to an edge weight between two episodes
_W_SIGNATURE = 0.5
_W_SYMBOLS = 0.3
_W_FAMILY = 0.1
_W_TASK = 0.1


@dataclass
class EpisodeNode:
    index: int
    repo_family: str
    failure_signature: str
    task_type: str
    solved: bool
    recipe: tuple[str, ...]
    reward: float
    decay_score: float


@dataclass
class EpisodeGraph:
    nodes: list[EpisodeNode] = field(default_factory=list)
    adjacency: dict[int, dict[int, float]] = field(default_factory=dict)

    def neighbors(self, index: int, *, min_weight: float = 0.0) -> list[tuple[int, float]]:
        """Neighbouring episode indices and edge weights, strongest link first."""
        edges = [(j, w) for j, w in self.adjacency.get(index, {}).items() if w >= min_weight]
        return sorted(edges, key=lambda jw: (-jw[1], jw[0]))

    def related_signatures(self, failure_signature: str, *, min_weight: float = 0.2) -> list[str]:
        """Failure signatures linked to ``failure_signature`` via the graph (closest first)."""
        seeds = [n.index for n in self.nodes if n.failure_signature == failure_signature]
        scored: dict[str, float] = {}
        for s in seeds:
            for j, w in self.neighbors(s, min_weight=min_weight):
                sig = self.nodes[j].failure_signature
                if sig != failure_signature:
                    scored[sig] = max(scored.get(sig, 0.0), w)
        return [sig for sig, _ in sorted(scored.items(), key=lambda sw: (-sw[1], sw[0]))]


def _edge_weight(a: ExperienceEpisode, b: ExperienceEpisode) -> float:
    w = 0.0
    if a.failure_signature == b.failure_signature:
        w += _W_SIGNATURE
    sa, sb = set(a.changed_symbols), set(b.changed_symbols)
    if sa and sb:
        w += _W_SYMBOLS * (len(sa & sb) / len(sa | sb))      # symbol Jaccard
    if a.repo_family == b.repo_family:
        w += _W_FAMILY
    if a.task_type == b.task_type:
        w += _W_TASK
    return round(w, 6)


def build_episode_graph(episodes: list[ExperienceEpisode], *, tenant: str | None = None,
                        min_decay: float = 0.05) -> EpisodeGraph:
    """Build the graph over live (non-quarantined, in-tenant, non-decayed) episodes."""
    live = [
        ep for ep in episodes
        if not ep.quarantined
        and (tenant is None or ep.privacy_scope == tenant)
        and ep.decay_score >= min_decay
    ]
    nodes = [
        EpisodeNode(index=i, repo_family=ep.repo_family, failure_signature=ep.failure_signature,
                    task_type=ep.task_type, solved=ep.verifier_outcome == "solved",
                    recipe=ep.recipe, reward=ep.reward, decay_score=ep.decay_score)
        for i, ep in enumerate(live)
    ]
    adjacency: dict[int, dict[int, float]] = {i: {} for i in range(len(live))}
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            w = _edge_weight(live[i], live[j])
            if w > 0.0:
                adjacency[i][j] = w
                adjacency[j][i] = w
    return EpisodeGraph(nodes=nodes, adjacency=adjacency)


@dataclass
class RecipeRecommendation:
    recipe: tuple[str, ...]
    source: str                 # "direct" | "transferred" | "none"
    from_signature: str = ""    # the related signature a transferred recipe came from
    confidence: float = 0.0     # recency-weighted reward of the chosen episode (0 for none)


def recommend_recipe(episodes: list[ExperienceEpisode], *, failure_signature: str,
                     tenant: str | None = None, include_related: bool = True
                     ) -> RecipeRecommendation:
    """Best known-good lever SEQUENCE to replay for ``failure_signature``.

    Direct: among solved episodes with this signature that recorded a non-empty recipe, take the
    one with the highest recency-weighted reward. If none and ``include_related``, transfer the
    recipe from the closest related signature in the episode graph. Returns an empty ``"none"``
    recommendation when there is no usable procedure (caller falls back to normal routing).
    """
    graph = build_episode_graph(episodes, tenant=tenant)

    def _best_for(sig: str) -> tuple[ExperienceEpisode, float] | None:
        cands = [
            ep for ep in episodes
            if ep.failure_signature == sig and ep.verifier_outcome == "solved" and ep.recipe
            and not ep.quarantined and (tenant is None or ep.privacy_scope == tenant)
            and ep.decay_score >= 0.05
        ]
        if not cands:
            return None
        best = max(cands, key=lambda e: e.reward * e.decay_score)
        return best, round(best.reward * best.decay_score, 6)

    direct = _best_for(failure_signature)
    if direct is not None:
        return RecipeRecommendation(recipe=direct[0].recipe, source="direct",
                                    confidence=direct[1])
    if include_related:
        for sig in graph.related_signatures(failure_signature):
            rel = _best_for(sig)
            if rel is not None:
                return RecipeRecommendation(recipe=rel[0].recipe, source="transferred",
                                            from_signature=sig, confidence=rel[1])
    return RecipeRecommendation(recipe=(), source="none")
