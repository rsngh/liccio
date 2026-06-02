"""Preference-reward integration (WS6) + drift lifecycle (WS5)."""

from __future__ import annotations

from acp.learning.drift import WindowedOutcome
from acp.learning.drift_lifecycle import run_drift_lifecycle
from acp.learning.preference_reward import (
    PreferenceRewardCombiner,
    PreferenceRewardGate,
)


# ---- WS6 -----------------------------------------------------------------
def test_preference_reward_disabled_until_gate_passes() -> None:
    combiner = PreferenceRewardCombiner(preference_weight=0.5)
    # Before the gate, preference reward is ignored.
    assert combiner.combine(1.0, 10.0) == 1.0
    assert "preference" not in combiner.components(1.0, 10.0)


def test_gate_blocks_low_quality_preference_model() -> None:
    gate = PreferenceRewardGate()
    res = gate.evaluate(reviewer_agreement=0.5, pairwise_accuracy=0.55,
                        post_merge_correlation=-0.1, high_risk_degradation=0.2)
    assert res["passed"] is False
    assert "pairwise_accuracy" in res["reasons"]


def test_gate_passes_then_combined_reward_uses_preference() -> None:
    gate = PreferenceRewardGate()
    combiner = PreferenceRewardCombiner(preference_weight=0.5)
    res = gate.evaluate(reviewer_agreement=0.8, pairwise_accuracy=0.85,
                        post_merge_correlation=0.3, high_risk_degradation=0.0)
    assert combiner.apply_gate(res) is True
    assert combiner.combine(1.0, 2.0) == 2.0  # 1.0 + 0.5*2.0
    comps = combiner.components(1.0, 2.0)
    assert comps["objective"] == 1.0 and comps["preference"] == 1.0


# ---- WS5 -----------------------------------------------------------------
class _Ens:
    learned_promoted = True


def test_drift_lifecycle_demotes_and_opens_review_on_high_risk_fn() -> None:
    baseline = [WindowedOutcome(0.9 if i % 2 == 0 else 0.1, i % 2 == 0, "low", i)
                for i in range(40)]
    # Recent: confident "viable" predictions on high-risk tasks that were NOT viable.
    recent = [WindowedOutcome(0.9, False, "high", 100 + i) for i in range(20)]
    ens = _Ens()
    result = run_drift_lifecycle(ens, model_name="learned_viability",
                                 baseline=baseline, recent=recent)
    assert result.demoted is True
    assert ens.learned_promoted is False
    assert result.demotion_event is not None
    assert result.review_item is not None  # high-risk FN -> human review opened
    assert result.review_item.priority == 1.0


def test_drift_lifecycle_no_demotion_when_stable() -> None:
    stable = [WindowedOutcome(0.9 if i % 2 == 0 else 0.1, i % 2 == 0, "low", i)
              for i in range(40)]
    ens = _Ens()
    result = run_drift_lifecycle(ens, model_name="learned_viability",
                                 baseline=stable, recent=stable[:20])
    assert result.demoted is False
    assert ens.learned_promoted is True
    assert result.review_item is None
