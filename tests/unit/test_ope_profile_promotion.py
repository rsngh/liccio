"""Profile-aware policy promotion blocking (Alpha 14 WS5 v3)."""

from __future__ import annotations

from acp.routing.ope import (
    OPESample,
    is_policy_promotable_under_profile,
    policy_value_under_profile,
)


def _always(action: str):
    def pi(ctx, a, cands):
        return 1.0 if a == action else 0.0
    return pi


def test_contaminated_high_success_policy_blocked_under_trust_profile() -> None:
    # 'dirty' solves every time but on contaminated measurement (quality 0.3);
    # 'clean' solves on trustworthy measurement (quality 1.0).
    cands = ["clean", "dirty"]
    samples = ([OPESample("c", "clean", 0.5, 1.0, cands, measurement_quality=1.0)
                for _ in range(6)]
               + [OPESample("c", "dirty", 0.5, 1.0, cands, measurement_quality=0.3)
                  for _ in range(6)])
    clean_v = policy_value_under_profile(samples, _always("clean"), "measurement_trust_max")
    dirty_v = policy_value_under_profile(samples, _always("dirty"), "measurement_trust_max")
    assert clean_v > dirty_v
    # The contaminated policy is blocked at a trust threshold the clean one clears.
    thr = (clean_v + dirty_v) / 2
    assert is_policy_promotable_under_profile(
        samples, _always("clean"), profile="measurement_trust_max", min_value=thr)
    assert not is_policy_promotable_under_profile(
        samples, _always("dirty"), profile="measurement_trust_max", min_value=thr)


def test_costly_policy_blocked_under_cost_saver() -> None:
    cands = ["cheap", "pricey"]
    samples = ([OPESample("c", "cheap", 0.5, 1.0, cands, cost=0.001) for _ in range(6)]
               + [OPESample("c", "pricey", 0.5, 1.0, cands, cost=0.05) for _ in range(6)])
    cheap_v = policy_value_under_profile(samples, _always("cheap"), "cost_saver")
    pricey_v = policy_value_under_profile(samples, _always("pricey"), "cost_saver")
    assert cheap_v > pricey_v
