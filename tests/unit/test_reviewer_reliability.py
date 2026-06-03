"""Tests for reviewer reliability + preference-reward governance (Alpha 11 WS7)."""

from __future__ import annotations

import json

from acp.core.enums import HumanVerdict
from acp.learning.preference_reward import PreferenceRewardGate
from acp.learning.reviewer_reliability import (
    ReviewerReliabilityModel,
    default_governance_dataset,
    evaluate_preference_reward_governance,
)
from acp.schemas.human_review import HumanLabel


def _label(attempt: str, verdict: HumanVerdict, reviewer: str) -> HumanLabel:
    return HumanLabel(
        review_item_id=f"ri-{attempt}-{reviewer}",
        task_id=attempt.split("-")[0],
        attempt_id=attempt,
        verdict=verdict,
        reviewer=reviewer,
    )


def test_correct_reviewer_more_reliable_than_random() -> None:
    truth = {"t1-good": True, "t1-bad": False, "t2-good": True, "t2-bad": False}
    labels = [
        # always-correct reviewer
        _label("t1-good", HumanVerdict.PASS, "honest"),
        _label("t1-bad", HumanVerdict.FAIL, "honest"),
        _label("t2-good", HumanVerdict.PASS, "honest"),
        _label("t2-bad", HumanVerdict.FAIL, "honest"),
        # random/wrong reviewer
        _label("t1-good", HumanVerdict.FAIL, "random"),
        _label("t1-bad", HumanVerdict.PASS, "random"),
        _label("t2-good", HumanVerdict.FAIL, "random"),
        _label("t2-bad", HumanVerdict.PASS, "random"),
    ]
    model = ReviewerReliabilityModel()
    model.fit(labels, truth)
    rel = model.reliability_by_reviewer()
    assert rel["honest"] == 1.0
    assert rel["random"] == 0.0
    assert rel["honest"] > rel["random"]
    assert model.agreement() == 0.5  # micro-average over all labels


def test_governance_promotes_when_all_thresholds_pass() -> None:
    labels, features, truth = default_governance_dataset()
    result = evaluate_preference_reward_governance(
        labels,
        features,
        truth_by_attempt=truth,
        post_merge_correlation=0.5,
        high_risk_degradation=0.0,
    )
    assert result["pairwise_accuracy"] >= 0.7
    assert result["reviewer_agreement"] >= 0.7
    assert result["gate"]["passed"] is True
    assert result["promoted"] is True


def test_governance_advisory_on_low_agreement() -> None:
    labels, features, truth = default_governance_dataset()
    # No ground truth -> reviewer_agreement defaults to 0.0 -> blocks promotion.
    result = evaluate_preference_reward_governance(
        labels,
        features,
        truth_by_attempt=None,
        post_merge_correlation=0.5,
    )
    assert result["reviewer_agreement"] == 0.0
    assert result["promoted"] is False
    assert "reviewer_agreement" in result["gate"]["reasons"]


def test_governance_advisory_on_low_pairwise_accuracy() -> None:
    # A single tied/degenerate task yields no usable pairs -> 0.0 accuracy.
    labels = [_label("x-a", HumanVerdict.PASS, "alice")]
    features = {"x-a": {"verified": 1.0}}
    gate = PreferenceRewardGate(min_pairwise_accuracy=0.9)
    result = evaluate_preference_reward_governance(
        labels,
        features,
        truth_by_attempt={"x-a": True},
        post_merge_correlation=0.5,
        gate=gate,
    )
    assert result["pairwise_accuracy"] < 0.9
    assert result["promoted"] is False
    assert "pairwise_accuracy" in result["gate"]["reasons"]


def test_governance_result_json_serializable() -> None:
    labels, features, truth = default_governance_dataset()
    result = evaluate_preference_reward_governance(
        labels, features, truth_by_attempt=truth, post_merge_correlation=0.5
    )
    assert json.loads(json.dumps(result)) == result
