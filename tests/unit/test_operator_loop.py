"""Operator learning loop tests (GOALS Alpha 44 P9)."""

from __future__ import annotations

from acp.review.operator_loop import (
    ReviewItem,
    active_learning_queue,
    label_quality,
    policy_update_from_labels,
)


def test_active_learner_prioritizes_uncertain_risky_recurring() -> None:
    items = [
        ReviewItem("a", "docs", uncertainty=0.2, risk_level="low", bucket_frequency=1),
        ReviewItem("b", "security", uncertainty=0.9, risk_level="high", bucket_frequency=8),
        ReviewItem("c", "bugfix", uncertainty=0.5, risk_level="medium", bucket_frequency=2),
    ]
    q = active_learning_queue(items, k=3)
    assert q[0].task_id == "b"           # high uncertainty x high risk x recurring -> top
    assert "priority" in q[0].why()


def test_label_quality_tracks_agreement_and_near_miss() -> None:
    labels = [
        {"bucket": "x", "reviewers": ["reject", "reject"], "system_verdict": "approve"},  # near miss
        {"bucket": "x", "reviewers": ["approve", "reject"], "system_verdict": "approve"},  # disagree
        {"bucket": "y", "reviewers": ["approve", "approve"], "system_verdict": "approve"},  # agree
    ]
    q = label_quality(labels)
    assert q.n_labels == 3
    assert q.false_auto_approve_near_miss == 1
    assert 0.0 <= q.reviewer_agreement <= 1.0


def test_label_changes_future_routing_when_reviewers_agree() -> None:
    labels = [{"bucket": "cross_file", "reviewers": ["repo_map", "repo_map"],
               "preferred_action": "repo_map_router", "risk_level": "medium"}]
    out = policy_update_from_labels(labels, {"cross_file": "cheap_single"})
    assert out["new_routing"]["cross_file"] == "repo_map_router"
    assert out["n_applied"] == 1


def test_disagreement_blocks_learning() -> None:
    labels = [{"bucket": "b", "reviewers": ["a", "z"], "preferred_action": "grep_router"}]
    out = policy_update_from_labels(labels, {"b": "cheap_single"})
    assert out["n_applied"] == 0
    assert out["new_routing"]["b"] == "cheap_single"


def test_high_risk_label_stays_advisory() -> None:
    labels = [{"bucket": "sec", "reviewers": ["strict", "strict"],
               "preferred_action": "strict_verify", "risk_level": "high"}]
    out = policy_update_from_labels(labels, {"sec": "cheap_single"})
    assert out["n_applied"] == 0
    assert "advisory" in out["updates"][0]["reason"]
