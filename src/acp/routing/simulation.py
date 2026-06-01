"""Synthetic bandit environment + simulation harness (charter §13.4, §20.3).

Three arms with context-dependent success/cost (Agent A cheap/ok, B expensive/
strong, C cheap-for-docs/bad-for-security). Used by the bandit Monte Carlo and
the bandit demo to show the policy learns a better-than-random routing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction

CONTEXTS = ["docs", "bugfix", "security"]

# success probability per (context, arm)
SUCCESS = {
    "docs": {"A": 0.85, "B": 0.80, "C": 0.90},
    "bugfix": {"A": 0.55, "B": 0.85, "C": 0.45},
    "security": {"A": 0.40, "B": 0.88, "C": 0.20},
}
COST = {"A": 0.2, "B": 1.0, "C": 0.15}


def _arms() -> list[RoutingAction]:
    return [
        RoutingAction(agent_kind="fake", agent_name="A"),
        RoutingAction(agent_kind="fake", agent_name="B"),
        RoutingAction(agent_kind="fake", agent_name="C"),
    ]


def _reward_for(ctx: str, arm: str, rng: random.Random) -> float:
    success = 1.0 if rng.random() < SUCCESS[ctx][arm] else 0.0
    return 3.0 * success - 0.5 * COST[arm]


def _best_expected(ctx: str) -> float:
    return max(3.0 * SUCCESS[ctx][a] - 0.5 * COST[a] for a in ("A", "B", "C"))


@dataclass
class SimResult:
    policy_reward: float = 0.0
    random_reward: float = 0.0
    regret: float = 0.0
    action_counts: dict[str, int] = field(default_factory=dict)
    rounds: int = 0

    @property
    def beats_random(self) -> bool:
        return self.policy_reward > self.random_reward


def run_simulation(
    policy: SimulatedBanditPolicy | None = None,
    rounds: int = 1000,
    seed: int = 1234,
    drift_at: int | None = None,
) -> SimResult:
    rng = random.Random(seed)
    policy = policy or SimulatedBanditPolicy(seed=seed, epsilon=0.1)
    arms = _arms()
    res = SimResult(rounds=rounds)
    success_table = {k: dict(v) for k, v in SUCCESS.items()}

    for t in range(rounds):
        if drift_at is not None and t == drift_at:
            # non-stationary shift: B degrades, A improves on bugfix
            success_table["bugfix"] = {"A": 0.9, "B": 0.4, "C": 0.45}

        ctx = rng.choice(CONTEXTS)
        features = {"task_type": ctx, "risk_level": "medium"}
        decision = policy.choose_action(features, arms)
        arm = decision.action.agent_name
        # reward using (possibly drifted) table
        succ = 1.0 if rng.random() < success_table[ctx][arm] else 0.0
        reward_val = 3.0 * succ - 0.5 * COST[arm]
        res.policy_reward += reward_val
        res.action_counts[arm] = res.action_counts.get(arm, 0) + 1

        reward = RewardEvent(
            task_id=f"sim_{t}", reward=reward_val,
            components={"sim": reward_val}, metadata={"ctx": ctx},
        )
        policy.observe_reward(decision, reward)

        # random baseline
        rand_arm = rng.choice(["A", "B", "C"])
        rand_succ = 1.0 if rng.random() < success_table[ctx][rand_arm] else 0.0
        res.random_reward += 3.0 * rand_succ - 0.5 * COST[rand_arm]

        res.regret += _best_expected(ctx) - reward_val

    return res


def make_decision_log(
    seed: int = 1234, rounds: int = 200
) -> list[tuple[PolicyDecision, RewardEvent]]:
    """Produce a (decision, reward) log for off-policy evaluation tests."""
    policy = SimulatedBanditPolicy(seed=seed)
    arms = _arms()
    rng = random.Random(seed)
    log: list[tuple[PolicyDecision, RewardEvent]] = []
    for t in range(rounds):
        ctx = rng.choice(CONTEXTS)
        decision = policy.choose_action({"task_type": ctx, "risk_level": "low"}, arms)
        r = _reward_for(ctx, decision.action.agent_name, rng)
        reward = RewardEvent(
            task_id=f"t{t}", reward=r, components={"sim": r}, metadata={"ctx": ctx}
        )
        policy.observe_reward(decision, reward)
        log.append((decision, reward))
    return log
