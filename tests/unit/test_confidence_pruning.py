"""DeepConf-style confidence pruning (Alpha 24 area 14)."""

from __future__ import annotations

from acp.orchestration.confidence_pruning import (
    ScoredCandidate,
    confidence_weighted_vote,
    prune_by_confidence,
    should_early_stop,
)


def _cands(confs, answers=None):
    return [ScoredCandidate(index=i, confidence=c,
                            answer_key=(answers[i] if answers else None))
            for i, c in enumerate(confs)]


def test_prunes_low_confidence_and_estimates_savings() -> None:
    r = prune_by_confidence(_cands([0.9, 0.8, 0.2, 0.1]), threshold=0.5, min_keep=1,
                            cost_per_verify=0.01)
    assert r.kept == [0, 1] and r.pruned == [2, 3]
    assert r.keep_fraction == 0.5
    assert r.estimated_verify_savings == 0.02  # 2 pruned * 0.01


def test_never_prunes_below_min_keep() -> None:
    r = prune_by_confidence(_cands([0.1, 0.2, 0.15]), threshold=0.9, min_keep=2)
    assert len(r.kept) == 2  # topped up to the floor even though all below threshold


def test_high_risk_keeps_conservative_floor() -> None:
    r = prune_by_confidence(_cands([0.95, 0.1, 0.1, 0.1, 0.1]), threshold=0.9, min_keep=1,
                            risk="high")
    assert len(r.kept) >= 3  # high-risk floor protects verification


def test_confidence_weighted_vote_picks_highest_mass() -> None:
    # answer "B" has lower single confidence but more total mass than "A"
    cands = _cands([0.6, 0.5, 0.5], answers=["A", "B", "B"])
    assert confidence_weighted_vote(cands) == "B"
    assert confidence_weighted_vote(_cands([0.5])) is None  # no answer keys


def test_early_stop_on_high_confidence() -> None:
    assert should_early_stop(_cands([0.5, 0.92]), high_conf_threshold=0.9)
    assert not should_early_stop(_cands([0.5, 0.7]), high_conf_threshold=0.9)
    # high-risk raises the bar -> 0.92 no longer triggers
    assert not should_early_stop(_cands([0.92]), high_conf_threshold=0.9, risk="high")


def test_empty_candidates() -> None:
    r = prune_by_confidence([])
    assert r.kept == [] and "no candidates" in r.rationale
