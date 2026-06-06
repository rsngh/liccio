"""Compute escalation policy v2 (Alpha 38)."""

from __future__ import annotations

import pytest

from acp.orchestration.compute_policy_v2 import (
    ComputeContextV2,
    ComputeSpendLedgerV2,
    choose_arm_v2,
)


def test_high_reliability_uses_cheap_single() -> None:
    d = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.95))
    assert d.arm == "cheap_single" and d.failure_mode == "none" and not d.escalated


def test_variance_failure_uses_best_of_k() -> None:
    d = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.6, best_of_k_lift=0.3))
    assert d.arm == "best_of_k" and d.failure_mode == "variance" and d.escalated


def test_systematic_failure_uses_advisor() -> None:
    d = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.2, best_of_k_lift=0.0))
    assert d.arm == "cheap_plus_advisor" and d.failure_mode == "systematic"


def test_systematic_high_risk_uses_frontier_plus_verifier() -> None:
    d = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.1, best_of_k_lift=0.0,
                                       risk="high"))
    assert d.arm == "frontier_plus_verifier"


def test_ambiguous_spec_asks_first() -> None:
    d = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.3, spec_ambiguous=True))
    assert d.arm == "ask_for_spec" and not d.escalated


def test_insufficient_evidence_abstains_or_asks() -> None:
    low = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.5,
                                         evidence_sufficient=False, risk="low"))
    assert low.arm == "abstain"
    high = choose_arm_v2(ComputeContextV2(single_shot_reliability=0.5,
                                          evidence_sufficient=False, risk="high"))
    assert high.arm == "ask_for_spec"


def test_marginal_value_report() -> None:
    lg = ComputeSpendLedgerV2()
    for _ in range(10):
        lg.record("cheap_single", solved=False, cost=0.001)
    for _ in range(10):
        lg.record("cheap_plus_advisor", solved=True, cost=0.02)
    rep = lg.marginal_value_report()
    advisor = next(r for r in rep["rows"] if r["arm"] == "cheap_plus_advisor")
    assert advisor["solve_lift"] == 1.0 and advisor["marginal_value_positive"]


def test_bad_arm_rejected() -> None:
    with pytest.raises(ValueError):
        ComputeSpendLedgerV2().record("teleport", solved=True, cost=0.0)
