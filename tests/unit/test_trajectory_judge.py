"""Tests for the relative trajectory judge (Alpha 11/12 §WS9)."""

from __future__ import annotations

import json

from acp.evaluation.trajectory_judge import (
    RelativeTrajectoryJudge,
    default_pair_context,
    default_trajectory_pair,
)
from acp.schemas.workspace import DiffBundle


def _compare_default():
    a, b = default_trajectory_pair()
    ctx_a, ctx_b = default_pair_context()
    judge = RelativeTrajectoryJudge()
    comparison = judge.compare(
        a,
        b,
        solved_a=ctx_a.solved,
        solved_b=ctx_b.solved,
        diff_a=ctx_a.diff,
        diff_b=ctx_b.diff,
    )
    return judge, a, b, ctx_a, ctx_b, comparison


def test_clearly_better_trajectory_wins_overall_and_most_axes():
    _, _, _, _, _, comparison = _compare_default()
    assert comparison.overall_winner == "a"
    assert comparison.margin > 0
    a_wins = sum(1 for r in comparison.per_axis if r.winner == "a")
    b_wins = sum(1 for r in comparison.per_axis if r.winner == "b")
    assert a_wins > b_wins


def test_test_deleting_trajectory_loses_security_axis():
    _, _, _, _, _, comparison = _compare_default()
    security = next(r for r in comparison.per_axis if r.axis == "security")
    # A (no deletion) scores higher than B (deleted test) -> A wins security.
    assert security.winner == "a"
    assert security.score_a > security.score_b


def test_minimality_prefers_smaller_diff():
    _, _, _, _, _, comparison = _compare_default()
    minimality = next(r for r in comparison.per_axis if r.axis == "minimality")
    assert minimality.winner == "a"
    assert minimality.score_a > minimality.score_b


def test_cross_judge_audit_high_for_dominant_winner():
    judge, _, _, _, _, comparison = _compare_default()
    audit = judge.cross_judge_audit(comparison)
    assert audit.axes_agreement >= 0.5


def test_reward_sensitivity_returns_influence_per_axis():
    judge, a, b, ctx_a, ctx_b, _ = _compare_default()
    report = judge.reward_sensitivity(
        a,
        b,
        solved_a=ctx_a.solved,
        solved_b=ctx_b.solved,
        diff_a=ctx_a.diff,
        diff_b=ctx_b.diff,
    )
    assert set(report.influence) == set(judge.axes)
    assert all(v >= 0.0 for v in report.influence.values())


def test_to_preference_yields_better_trace_as_winner():
    judge, _, _, _, _, comparison = _compare_default()
    features_a = {"quality": 1.0}
    features_b = {"quality": 0.0}
    pref = judge.to_preference(comparison, features_a, features_b)
    assert pref is not None
    assert pref.winner_features == features_a
    assert pref.loser_features == features_b


def test_tie_yields_no_preference():
    a, b = default_trajectory_pair()
    judge = RelativeTrajectoryJudge()
    diff = DiffBundle(changed_files=[], insertions=0, deletions=0)
    # Identical trace compared against itself -> every axis ties.
    comparison = judge.compare(a, a, solved_a=True, solved_b=True, diff_a=diff, diff_b=diff)
    assert comparison.overall_winner == "tie"
    assert judge.to_preference(comparison, {"x": 1.0}, {"x": 0.0}) is None


def test_comparison_json_serializable():
    _, _, _, _, _, comparison = _compare_default()
    payload = comparison.model_dump(mode="json")
    text = json.dumps(payload)
    assert json.loads(text)["overall_winner"] == "a"
