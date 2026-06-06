"""Coordination policy graph v2 (Alpha 33)."""

from __future__ import annotations

import pytest

from acp.routing.policy_graph import (
    PolicyGraph,
    fold,
    reward_audit,
    skip_policy,
)


def test_fold_buckets_continuous_dims() -> None:
    sig = fold(task_regime="bugfix", risk="low", spec_clarity=0.2,
               single_shot_reliability=0.84, measurement_quality=0.5)
    assert sig.ambiguity == "ambiguous" and sig.reliability == "medium"
    assert sig.measurement == "untrusted"
    assert "bugfix|low|ambiguous" in sig.key()


def test_only_conclusive_rewards_update_policy() -> None:
    g = PolicyGraph()
    sig = fold(task_regime="bugfix")
    g.update(sig, "best_of_k", 1.0, conclusive=False)   # ignored
    assert g.value(sig, "best_of_k") == (0.0, 0)
    g.update(sig, "best_of_k", 1.0, conclusive=True)
    assert g.value(sig, "best_of_k") == (1.0, 1)


def test_best_action_prefers_higher_value() -> None:
    g = PolicyGraph()
    sig = fold(task_regime="bugfix", single_shot_reliability=0.6)
    for _ in range(3):
        g.update(sig, "best_of_k", 1.0)
        g.update(sig, "consult_advisor", 0.2)
    action, reason = g.best_action(sig, ["best_of_k", "consult_advisor"])
    assert action == "best_of_k" and "signature-local" in reason


def test_global_fallback_for_unseen_signature() -> None:
    g = PolicyGraph()
    g.update(fold(task_regime="bugfix"), "best_of_k", 1.0)
    # a different signature with no local evidence falls back to the global value
    other = fold(task_regime="refactor", risk="high")
    action, reason = g.best_action(other, ["best_of_k", "consult_advisor"])
    assert action == "best_of_k" and "global fallback" in reason


def test_warm_start_transfers_evidence() -> None:
    src = PolicyGraph()
    sig = fold(task_regime="bugfix")
    for _ in range(4):
        src.update(sig, "best_of_k", 1.0)
    dst = PolicyGraph()
    assert dst.value(sig, "best_of_k") == (0.0, 0)
    dst.warm_start(src, weight=0.5)
    mean, n = dst.value(sig, "best_of_k")
    assert mean > 0 and n >= 1   # transferred at a discount


def test_skip_policy_never_skips_verify_on_high_risk() -> None:
    low = skip_policy(fold(task_regime="bugfix", risk="low", single_shot_reliability=0.95))
    assert "skip:planner" in low["skips"] and "skip:retrieval" in low["skips"]
    high = skip_policy(fold(task_regime="security_fix", risk="high"))
    assert high["strict_verify"] and "skip:retrieval" not in high["skips"]


def test_reward_audit_can_block_promotion() -> None:
    assert not reward_audit(0.9, 0.88)["promotion_blocked"]   # agree
    blocked = reward_audit(0.9, 0.4)
    assert blocked["promotion_blocked"] and "block" in blocked["reason"]


def test_unknown_action_rejected() -> None:
    with pytest.raises(ValueError):
        PolicyGraph().update(fold(task_regime="bugfix"), "nuke", 1.0)
