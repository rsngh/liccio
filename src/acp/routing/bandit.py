"""Contextual bandit policies (charter §13.4).

`SimulatedBanditPolicy` is the always-available fallback (no optional deps). It
supports epsilon-greedy and Thompson sampling over per-context arms, with a
seeded RNG so tests are deterministic. MABWiser/VW backends plug in behind the
same RoutingPolicy protocol when installed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from acp.core.enums import ExplorationMode
from acp.routing.features import RoutingFeatureExtractor
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction


@dataclass
class ArmStats:
    n: int = 0
    mean: float = 0.0
    # Beta params for Thompson over a normalized [0,1] success proxy.
    alpha: float = 1.0
    beta: float = 1.0

    def update(self, reward: float, success: float) -> None:
        self.n += 1
        self.mean += (reward - self.mean) / self.n
        self.alpha += success
        self.beta += 1.0 - success


@dataclass
class SimulatedBanditPolicy:
    policy_version: str = "bandit-sim-v1"
    epsilon: float = 0.1
    mode: str = "epsilon_greedy"  # epsilon_greedy | thompson
    seed: int = 1234
    arms: dict[str, dict[str, ArmStats]] = field(default_factory=dict)
    _rng: random.Random = field(default_factory=lambda: random.Random(1234))

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._extractor = RoutingFeatureExtractor()

    def _ctx(self, features: dict) -> str:
        return RoutingFeatureExtractor.context_key(features)  # type: ignore[arg-type]

    def _stats(self, ctx: str, action_key: str) -> ArmStats:
        return self.arms.setdefault(ctx, {}).setdefault(action_key, ArmStats())

    def choose_action(self, features: dict, candidates: list[RoutingAction]) -> PolicyDecision:
        ctx = self._ctx(features)
        ctx_arms = self.arms.setdefault(ctx, {})
        for a in candidates:
            ctx_arms.setdefault(a.key(), ArmStats())

        scores: dict[str, float] = {}
        mode = ExplorationMode.EXPLOIT
        reason = "exploit best mean"

        if self.mode == "thompson":
            for a in candidates:
                s = ctx_arms[a.key()]
                scores[a.key()] = self._rng.betavariate(s.alpha, s.beta)
            mode = ExplorationMode.EXPLORE
            reason = "thompson sample"
            chosen = max(candidates, key=lambda a: scores[a.key()])
            prob = 1.0 / len(candidates)  # approximate propensity
        else:
            for a in candidates:
                scores[a.key()] = ctx_arms[a.key()].mean
            if self._rng.random() < self.epsilon:
                chosen = self._rng.choice(candidates)
                mode = ExplorationMode.EXPLORE
                reason = f"epsilon-greedy explore (eps={self.epsilon})"
                prob = self.epsilon / len(candidates)
            else:
                best_mean = max(scores[a.key()] for a in candidates)
                best = [a for a in candidates if scores[a.key()] == best_mean]
                chosen = self._rng.choice(best)
                prob = (1 - self.epsilon) / len(best) + self.epsilon / len(candidates)

        return PolicyDecision(
            policy_version=self.policy_version,
            action=chosen,
            action_probability=max(1e-6, min(1.0, prob)),
            context_key=ctx,
            candidate_scores=scores,
            exploration_mode=mode,
            exploration_reason=reason,
            seed=self.seed,
        )

    def export_arms(self) -> dict:
        """Serialize per-context arm stats (for durable PolicyState)."""
        return {
            ctx: {k: {"n": s.n, "mean": s.mean, "alpha": s.alpha, "beta": s.beta}
                  for k, s in arms.items()}
            for ctx, arms in self.arms.items()
        }

    def import_arms(self, data: dict) -> None:
        """Restore per-context arm stats from a persisted PolicyState."""
        self.arms = {}
        for ctx, arms in (data or {}).items():
            self.arms[ctx] = {
                k: ArmStats(n=int(v.get("n", 0)), mean=float(v.get("mean", 0.0)),
                            alpha=float(v.get("alpha", 1.0)), beta=float(v.get("beta", 1.0)))
                for k, v in arms.items()
            }

    def observe_reward(self, decision: PolicyDecision, reward: RewardEvent) -> None:
        # Use the context recorded on the decision (falls back to reward metadata).
        ctx = decision.context_key or reward.metadata.get("ctx", "global")
        success = 1.0 if reward.reward > 0 else 0.0
        # normalize reward to [0,1]-ish via squashing for the running mean proxy
        norm = 1.0 / (1.0 + pow(2.718281828, -reward.reward))
        self._stats(ctx, decision.action.key()).update(norm, success)
