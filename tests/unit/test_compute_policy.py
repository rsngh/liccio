"""Compute-escalation policy + spend ledger (Alpha 29)."""

from __future__ import annotations

import pytest

from acp.orchestration.compute_policy import (
    ComputeSpendLedger,
    arms_summary,
    choose_arm,
)


def test_high_reliability_does_not_escalate() -> None:
    d = choose_arm(single_shot_reliability=0.95)
    assert d.arm == "cheap_single" and not d.escalated


def test_medium_reliability_uses_best_of_k() -> None:
    d = choose_arm(single_shot_reliability=0.6, value=0.8)
    assert d.arm == "cheap_best_of_k" and d.escalated


def test_low_reliability_high_risk_escalates_to_advisor() -> None:
    d = choose_arm(single_shot_reliability=0.2, risk="high")
    assert d.arm in ("cheap_advisor", "frontier_single") and d.escalated


def test_ledger_marginal_value() -> None:
    lg = ComputeSpendLedger()
    for _ in range(10):
        lg.record("cheap_single", 0.001, solved=False)
    for _ in range(8):
        lg.record("cheap_best_of_k", 0.008, solved=True)
    for _ in range(2):
        lg.record("cheap_best_of_k", 0.008, solved=False)
    mv = lg.marginal_value("cheap_best_of_k")
    assert mv["known"] and mv["solve_lift"] == 0.8 and mv["positive"]


def test_escalation_blocked_when_marginal_value_not_positive() -> None:
    # ledger shows best-of-k does NOT help -> policy refuses to escalate (low risk/value)
    lg = ComputeSpendLedger()
    for _ in range(10):
        lg.record("cheap_single", 0.001, solved=True)
    for _ in range(10):
        lg.record("cheap_best_of_k", 0.008, solved=True)   # same solve, more cost
    d = choose_arm(single_shot_reliability=0.6, risk="low", value=0.3, ledger=lg)
    assert d.arm == "cheap_single" and not d.escalated      # no positive marginal value


def test_arms_summary_shape() -> None:
    lg = ComputeSpendLedger()
    lg.record("cheap_single", 0.001, True)
    s = arms_summary(lg)
    assert set(s) == {"cheap_single", "cheap_best_of_k", "cheap_advisor", "frontier_single"}
    assert "marginal" in s["cheap_single"]


def test_bad_arm_rejected() -> None:
    with pytest.raises(ValueError):
        ComputeSpendLedger().record("quantum", 1.0, True)
