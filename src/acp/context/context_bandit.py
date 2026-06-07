"""Context-strategy bandit (GOALS Alpha 43 P5).

Online counterpart to ContextStrategyOPE: a per-``context_need`` epsilon-greedy bandit over
context strategies (none/grep/repo_map/hybrid/repo_map_plus_memory) that learns from verified
outcomes which strategy to pull, while exploring cheaply. Deterministic given a seed. Cost-aware:
ties on reward break toward the cheaper strategy.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

STRATEGIES = ("none", "grep", "repo_map", "hybrid_keyword_embedding", "repo_map_plus_memory")


@dataclass
class _Arm:
    n: int = 0
    reward_sum: float = 0.0
    cost_sum: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.n if self.n else 0.0

    @property
    def mean_cost(self) -> float:
        return self.cost_sum / self.n if self.n else 0.0


@dataclass
class ContextBandit:
    epsilon: float = 0.15
    seed: int = 1234
    strategies: tuple[str, ...] = STRATEGIES
    _arms: dict[tuple[str, str], _Arm] = field(default_factory=lambda: defaultdict(_Arm))
    _rng: random.Random = field(default_factory=lambda: random.Random(1234))

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def select(self, context_need: str) -> str:
        """Epsilon-greedy: explore with prob epsilon, else exploit best reward (cheap tiebreak)."""
        if self._rng.random() < self.epsilon:
            return self._rng.choice(self.strategies)
        scored = [(s, self._arms[(context_need, s)]) for s in self.strategies]
        # exploit: max mean reward, tiebreak on lower mean cost, then name for determinism
        best = max(scored, key=lambda x: (round(x[1].mean_reward, 6), -x[1].mean_cost, x[0]))
        return best[0]

    def update(self, context_need: str, strategy: str, *, reward: float, cost: float = 0.0) -> None:
        arm = self._arms[(context_need, strategy)]
        arm.n += 1
        arm.reward_sum += reward
        arm.cost_sum += cost

    def best(self, context_need: str) -> str | None:
        seen = [(s, self._arms[(context_need, s)]) for s in self.strategies
                if self._arms[(context_need, s)].n > 0]
        if not seen:
            return None
        return max(seen, key=lambda x: (x[1].mean_reward, -x[1].mean_cost, x[0]))[0]

    def policy(self) -> dict[str, str | None]:
        needs = {need for (need, _) in self._arms}
        return {need: self.best(need) for need in sorted(needs)}

    def stats(self) -> dict:
        return {f"{need}|{strat}": {"n": a.n, "mean_reward": round(a.mean_reward, 4),
                                    "mean_cost": round(a.mean_cost, 6)}
                for (need, strat), a in sorted(self._arms.items())}
