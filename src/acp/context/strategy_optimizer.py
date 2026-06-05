"""Context-strategy optimizer: grep vs embeddings vs hybrid (Alpha 24 area 6).

"Is Grep All You Need?" finds grep-style search can match or beat embedding retrieval on
coding-agent tasks when wrapped in a good harness, and that harness design often dominates
the retrieval primitive. The Efficiency Frontier frames context choice as deployment-aware
optimization over performance, token cost, and reuse. So the strategy must be chosen by
DOWNSTREAM success per cost — not recall alone — and grep is allowed to win.

This module scores observed (strategy -> downstream_success, tokens, latency, reuse)
evidence with a cost-adjusted reward, amortizes one-time index build cost over reuse, and
picks the strategy with the best evidence — emitting a policy-dossier rationale. Embedding
is never the default unless its downstream evidence justifies its cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STRATEGIES = ("grep", "embedding", "hybrid", "full_file", "symbol_graph")
# $/1k tokens proxy + one-time index build cost (tokens) amortized over reuse.
_TOKEN_COST_PER_1K = 0.002


@dataclass
class ContextObservation:
    strategy: str
    downstream_success: float        # 0..1 task success when this strategy fed the agent
    tokens: int                      # context tokens spent per task
    latency_s: float
    index_build_tokens: int = 0      # one-time cost (e.g. embedding the repo)
    reuse_count: int = 1             # tasks the index is amortized over

    def __post_init__(self) -> None:
        if self.strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {self.strategy}")


def amortized_cost(o: ContextObservation) -> float:
    """Per-task token cost including one-time index build amortized over reuse."""
    per_task_index = o.index_build_tokens / max(1, o.reuse_count)
    return round((o.tokens + per_task_index) / 1000.0 * _TOKEN_COST_PER_1K, 6)


@dataclass
class StrategyScore:
    strategy: str
    downstream_success: float
    cost: float
    cost_adjusted_reward: float      # success minus a small cost penalty
    latency_s: float

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def score_strategy(o: ContextObservation, *, cost_weight: float = 5.0) -> StrategyScore:
    cost = amortized_cost(o)
    return StrategyScore(strategy=o.strategy, downstream_success=round(o.downstream_success, 4),
                         cost=cost, latency_s=o.latency_s,
                         cost_adjusted_reward=round(o.downstream_success - cost_weight * cost, 6))


@dataclass
class ContextStrategyDecision:
    chosen: str
    reason: str
    scores: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"chosen": self.chosen, "reason": self.reason,
                "scores": [s.to_dict() for s in self.scores]}


def choose_strategy(observations: list[ContextObservation], *, cost_weight: float = 5.0
                    ) -> ContextStrategyDecision:
    """Pick the strategy with the best cost-adjusted downstream reward (grep may win).

    Ties on reward break toward LOWER cost, then lower latency — so a free primitive (grep)
    beats an embedding index that only matches it on success.
    """
    if not observations:
        return ContextStrategyDecision("grep", "no evidence -> cheapest default")
    scores = [score_strategy(o, cost_weight=cost_weight) for o in observations]
    best = max(scores, key=lambda s: (s.cost_adjusted_reward, -s.cost, -s.latency_s))
    emb = next((s for s in scores if s.strategy == "embedding"), None)
    note = ""
    if best.strategy != "embedding" and emb is not None:
        note = (f"; embedding not chosen (reward {emb.cost_adjusted_reward} <= "
                f"{best.cost_adjusted_reward} at higher cost {emb.cost})")
    reason = (f"{best.strategy}: cost-adjusted reward {best.cost_adjusted_reward} "
              f"(success {best.downstream_success} at cost {best.cost}){note}")
    return ContextStrategyDecision(chosen=best.strategy, reason=reason, scores=scores)
