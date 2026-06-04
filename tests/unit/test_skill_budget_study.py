"""Evolver budget study (Alpha 21 WS14)."""

from __future__ import annotations

from acp.training.skill_budget_study import BudgetObservation, analyze_budget


def test_picks_knee_not_max_budget() -> None:
    obs = [
        BudgetObservation(max_steps=1, best_score=0.6, rollout_cost=0.01),
        BudgetObservation(max_steps=3, best_score=0.98, rollout_cost=0.03),
        BudgetObservation(max_steps=8, best_score=1.0, rollout_cost=0.10),
    ]
    study = analyze_budget(obs)
    # 3 steps reaches 0.98 (within 0.02 of best 1.0) -> recommend 3, not 8.
    assert study.recommended_max_steps == 3 and study.best_score == 1.0


def test_recommends_min_when_all_equal() -> None:
    obs = [BudgetObservation(1, 1.0, 0.01), BudgetObservation(5, 1.0, 0.05)]
    assert analyze_budget(obs).recommended_max_steps == 1


def test_empty_is_safe() -> None:
    assert analyze_budget([]).recommended_max_steps == 0
