"""Cost-aware OPE v3 — profile target policies (Alpha 13 WS5)."""

from __future__ import annotations

from acp.routing.ope import (
    OPE_PROFILES,
    OPESample,
    evaluate_policy,
    greedy_target_for_profile,
    profile_reward,
)


def test_profiles_enumerated() -> None:
    assert set(OPE_PROFILES) == {
        "quality_max", "cost_saver", "balanced", "risk_min", "measurement_trust_max"}


def test_cost_saver_penalizes_cost() -> None:
    cheap = OPESample("c", "cheap", 0.5, 1.0, ["cheap", "pricey"], cost=0.001)
    pricey = OPESample("c", "pricey", 0.5, 1.0, ["cheap", "pricey"], cost=0.02)
    assert profile_reward(cheap, "cost_saver") > profile_reward(pricey, "cost_saver")
    # quality_max ignores cost -> equal.
    assert profile_reward(cheap, "quality_max") == profile_reward(pricey, "quality_max")


def test_measurement_trust_max_discounts_contaminated_wins() -> None:
    clean = OPESample("c", "a", 0.5, 1.0, ["a", "b"], measurement_quality=1.0)
    dirty = OPESample("c", "b", 0.5, 1.0, ["a", "b"], measurement_quality=0.4)
    assert profile_reward(clean, "measurement_trust_max") > \
        profile_reward(dirty, "measurement_trust_max")


def test_greedy_profile_target_blocks_high_cost_winner_under_cost_saver() -> None:
    # 'pricey' and 'cheap' both solve; under cost_saver the greedy target picks cheap.
    ctx, cands = "bugfix", ["cheap", "pricey"]
    log = ([OPESample(ctx, "cheap", 0.5, 1.0, cands, cost=0.001) for _ in range(6)]
           + [OPESample(ctx, "pricey", 0.5, 1.0, cands, cost=0.02) for _ in range(6)])
    tgt = greedy_target_for_profile(log, "cost_saver")
    assert tgt(ctx, "cheap", cands) == 1.0 and tgt(ctx, "pricey", cands) == 0.0
    # And the policy is evaluable by the OPE machinery.
    est = evaluate_policy(log, tgt, seed=1)
    assert est.dr.value > 0
