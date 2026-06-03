"""Cost-aware OPE / counterfactual regret (Alpha 11/12 WS7)."""

from __future__ import annotations

from acp.routing.counterfactual import cost_adjusted_regret, total_regret
from acp.routing.ope import OPESample, cost_adjusted_reward


def test_cost_adjusted_reward_orders_only_on_ties() -> None:
    # Equal success -> cheaper wins; a real success gap dominates the cost term.
    assert cost_adjusted_reward(1.0, 0.001) > cost_adjusted_reward(1.0, 0.02)
    assert cost_adjusted_reward(1.0, 0.05) > cost_adjusted_reward(0.0, 0.001)


def test_cost_adjusted_regret_penalizes_pricier_equal_quality_choice() -> None:
    # Two arms tie on success (both solve), but the logged policy always picked the
    # expensive one. Plain regret sees no regret; cost-adjusted regret does.
    ctx, cands = "bugfix", ["cheap", "pricey"]
    log = [OPESample(ctx, "pricey", 0.5, 1.0, cands) for _ in range(6)]
    costs = [0.02] * 6
    # ... and a few logged cheap solves so the cost-aware best arm is "cheap".
    log += [OPESample(ctx, "cheap", 0.5, 1.0, cands) for _ in range(6)]
    costs += [0.001] * 6
    plain = total_regret(log)
    cost_aware = cost_adjusted_regret(log, costs)
    assert plain["mean_regret"] == 0.0           # success-only: both arms equal
    assert cost_aware["mean_regret"] > 0.0       # cost-aware: pricey choices regret
    assert cost_aware["cost_weight"] == 2.0
