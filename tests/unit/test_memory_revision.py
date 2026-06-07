# ruff: noqa: E501
"""Aging-aware memory revision — offline tests (deterministic)."""

from __future__ import annotations

from acp.memory.experience_bank import ExperienceBank, ExperienceEpisode
from acp.memory.memory_revision import (
    avoid_by_recency,
    consolidate,
    net_strategy_scores,
    recommend_by_recency,
    recommend_recipe,
)


def _ep(strategy, outcome, reward, now, recipe=()):
    return ExperienceEpisode(repo_family="r", task_type="bugfix", failure_signature="sig",
                             context_strategy=strategy, agent="x",
                             verifier_outcome=outcome, reward=reward, privacy_scope="t",
                             created_at=now, recipe=recipe)


def test_recency_lets_a_lever_be_reused_after_old_failure_ages_out() -> None:
    bank = ExperienceBank()
    pol_write = lambda ep: bank.episodes.append(ep)  # direct, bypass policy for the test  # noqa: E731
    # old failure of "ctx", then recent successes
    pol_write(_ep("ctx", "failed", -0.2, 0.0))
    pol_write(_ep("ctx", "solved", 1.0, 5.0))
    pol_write(_ep("ctx", "solved", 1.0, 6.0))
    bank.decay(now=6.0, half_life=2.0)   # age episodes; old failure decays the most
    # ever-failed logic would avoid "ctx"; recency sees net-positive -> recommend it, don't avoid it
    assert recommend_by_recency(bank, tenant="t", failure_signature="sig") == "ctx"
    assert "ctx" not in avoid_by_recency(bank, tenant="t", failure_signature="sig")
    assert "ctx" in bank.avoid_strategies(tenant="t", failure_signature="sig")  # the old sticky behavior


def test_avoid_by_recency_flags_net_negative() -> None:
    bank = ExperienceBank()
    bank.episodes.append(_ep("cheap", "failed", -0.2, 0.0))
    bank.episodes.append(_ep("cheap", "failed", -0.2, 1.0))
    assert "cheap" in avoid_by_recency(bank, tenant="t", failure_signature="sig")


def test_consolidate_dedups_into_net_signal() -> None:
    bank = ExperienceBank()
    for i in range(4):
        bank.episodes.append(_ep("ctx", "solved", 1.0, float(i)))
    removed = consolidate(bank)
    assert removed == 3 and len([e for e in bank.episodes if e.context_strategy == "ctx"]) == 1
    assert net_strategy_scores(bank, tenant="t", failure_signature="sig")["ctx"] > 0


def test_recommend_recipe_returns_winning_sequence() -> None:
    bank = ExperienceBank()
    bank.episodes.append(_ep("ctx", "solved", 1.0, 1.0, recipe=("cheap", "ctx")))
    assert recommend_recipe(bank, tenant="t", failure_signature="sig") == ("cheap", "ctx")
