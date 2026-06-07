# ruff: noqa: E501
"""Increment-4 — repo playbook + calibrated stop, offline tests."""

from __future__ import annotations

from acp.context.repo_playbook import RepoPlaybook
from acp.verification.calibrated_stop import calibrated_stop


def test_playbook_accumulates_and_strengthens() -> None:
    pb = RepoPlaybook(repo_family="r")
    pb.record_success(failure_signature="s", rule="do X", now=1.0)
    pb.record_success(failure_signature="s", rule="do X", now=2.0)   # same -> strengthen
    pb.record_success(failure_signature="t", rule="do Y", now=3.0)
    assert pb.covers("s") and pb.covers("t")
    assert [x for x in pb.lessons if x.failure_signature == "s"][0].support == 2


def test_playbook_render_surfaces_relevant_first_and_bounds() -> None:
    pb = RepoPlaybook(repo_family="r", max_lessons=3)
    for i in range(6):
        pb.record_success(failure_signature=f"s{i}", rule=f"rule {i}", now=float(i))
    assert len(pb.lessons) <= 3                       # pruned/bounded
    pb.record_success(failure_signature="key", rule="the key rule", now=10.0)
    rendered = pb.render(failure_signature="key")
    assert "key" in rendered.splitlines()[1]          # relevant lesson first


def test_calibrated_stop_no_confident_but_wrong_commit() -> None:
    # high confidence + sufficient -> commit
    assert calibrated_stop(judge_confidence=0.9, sufficiency_score=0.9, risk_level="low").action == "commit"
    # weak confidence -> abstain (low risk), not commit
    assert calibrated_stop(judge_confidence=0.55, sufficiency_score=0.8, risk_level="low").action == "abstain"
    # insufficient context -> human review regardless of judge confidence
    assert calibrated_stop(judge_confidence=0.95, sufficiency_score=0.3, risk_level="low").action == "human_review"
    # high-risk uses a stricter bar -> 0.8 < 0.85 -> human
    assert calibrated_stop(judge_confidence=0.8, sufficiency_score=0.95, risk_level="high").action == "human_review"


def test_sufficiency_caps_confidence() -> None:
    # even a very confident judge is capped by low sufficiency
    d = calibrated_stop(judge_confidence=1.0, sufficiency_score=0.5, risk_level="low")
    assert d.confidence <= 0.75
