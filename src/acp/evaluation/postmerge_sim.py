"""Delayed outcome simulator + post-merge lab (round-5 WS8).

A bakeoff's immediate verdict ("did it solve + verify") is not the whole story:
code that passed CI can still be reverted, cause an incident, reopen an issue,
or regress production latency days later. This module synthesizes those delayed
outcomes for a bakeoff EvalRun and feeds the resulting (mostly negative) rewards
back into the routing policy — so a harness that looked great on day 0 can be
*downgraded* once delayed reality lands.

Deterministic: outcomes are drawn from a seeded RNG + per-adapter revert profile,
so experiments reproduce. Pure aside from the injected RNG.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Delayed outcome kinds and the reward delta each implies (relative to the
# day-0 reward). Negative kinds penalize; merged_clean lightly reinforces.
OUTCOME_REWARD_DELTA = {
    "merged_clean": 0.2,
    "review_rounds": -0.1,
    "issue_reopened": -0.4,
    "latency_regression": -0.6,
    "reverted": -1.0,
    "incident": -1.2,
}
NEGATIVE_OUTCOMES = {"reverted", "incident", "issue_reopened", "latency_regression"}


@dataclass
class DelayedOutcome:
    cell_name: str
    adapter: str
    task_type: str
    kind: str
    reward_delta: float
    days: int


def _task_type(cell: dict) -> str:
    return cell.get("task_type") or cell.get("task") or "unknown"


def simulate_outcomes(report: dict, *, revert_profile: dict[str, float] | None = None,
                      seed: int = 1234) -> list[DelayedOutcome]:
    """Assign a synthetic delayed outcome to each *successful* bakeoff cell.

    ``revert_profile`` maps adapter -> probability of a negative delayed outcome
    (default 0.2 for any adapter). Failures on day 0 get no delayed outcome.
    """
    rng = random.Random(seed)
    profile = revert_profile or {}
    outcomes: list[DelayedOutcome] = []
    for cell in report.get("cells", []):
        if not cell.get("success"):
            continue
        adapter = cell["adapter"]
        p_bad = profile.get(adapter, 0.2)
        roll = rng.random()
        if roll < p_bad:
            # pick a negative kind deterministically from the roll
            neg = sorted(NEGATIVE_OUTCOMES)
            kind = neg[int(roll / max(p_bad, 1e-9) * len(neg)) % len(neg)]
        else:
            kind = "merged_clean" if rng.random() > 0.3 else "review_rounds"
        outcomes.append(DelayedOutcome(
            cell_name=cell.get("name", f"{_task_type(cell)}/{adapter}"),
            adapter=adapter, task_type=_task_type(cell), kind=kind,
            reward_delta=OUTCOME_REWARD_DELTA[kind],
            days=rng.randint(1, 30)))
    return outcomes


def apply_outcomes_to_policy(policy, outcomes: list[DelayedOutcome]) -> dict:
    """Feed delayed outcomes back into the bandit as post-merge rewards."""
    from acp.routing.policy import PolicyDecision
    from acp.routing.replay import action_for_adapter, replay_context_key
    from acp.schemas.learning import RewardEvent

    applied = 0
    for o in outcomes:
        decision = PolicyDecision(
            policy_version=getattr(policy, "policy_version", "policy"),
            action=action_for_adapter(o.adapter),
            context_key=replay_context_key(o.task_type), action_probability=1.0)
        reward = RewardEvent(
            task_id="postmerge", reward=o.reward_delta, label_source="post_merge",
            components={"delayed_outcome": o.reward_delta},
            metadata={"kind": o.kind, "days": o.days, "outcome_source": "post_merge"})
        policy.observe_reward(decision, reward)
        applied += 1
    return {"applied": applied,
            "negative": sum(1 for o in outcomes if o.kind in NEGATIVE_OUTCOMES),
            "by_kind": _count_by_kind(outcomes)}


def _count_by_kind(outcomes: list[DelayedOutcome]) -> dict[str, int]:
    out: dict[str, int] = {}
    for o in outcomes:
        out[o.kind] = out.get(o.kind, 0) + 1
    return out


def outcomes_summary(outcomes: list[DelayedOutcome]) -> dict:
    return {
        "n": len(outcomes),
        "by_kind": _count_by_kind(outcomes),
        "negative_rate": round(
            sum(1 for o in outcomes if o.kind in NEGATIVE_OUTCOMES) / max(1, len(outcomes)), 3),
        "outcomes": [vars(o) for o in outcomes],
    }
