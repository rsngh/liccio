"""Skill economy v3 — value ledger + market (Alpha 39)."""

from __future__ import annotations

from acp.training.skill_market import (
    SkillMarket,
    SkillValueLedger,
    SkillValueObservation,
)


def _obs(skill, scope, base_s, skill_s, n=30, **kw):
    return SkillValueObservation(skill_id=skill, scope=scope, baseline_successes=base_s,
                                 baseline_n=n, skill_successes=skill_s, skill_n=n, **kw)


def test_market_crowns_robust_helper() -> None:
    m = SkillMarket()
    m.record(_obs("verify", "bugfix/low", 12, 28))      # robust help
    m.record(_obs("noise", "bugfix/low", 15, 16))       # negligible
    assert m.best_skill("bugfix/low") == "verify"
    board = m.leaderboard("bugfix/low")
    assert board[0]["skill_id"] == "verify" and board[0]["robustly_helps"]


def test_no_robust_helper_means_no_skill_deployed() -> None:
    m = SkillMarket()
    m.record(_obs("small", "x", 2, 3, n=3))             # tiny sample, not robust
    assert m.best_skill("x") is None


def test_degraded_observation_is_untrusted() -> None:
    m = SkillMarket()
    m.record(_obs("verify", "y", 27, 0, activation_rate=0.3))  # degraded -> untrusted
    assert m.best_skill("y") is None
    assert not m.leaderboard("y")[0]["trusted"]


def test_cost_adjusted_value_penalizes_expensive_skill() -> None:
    cheap = _obs("cheap", "z", 12, 24, baseline_cost=0.001, skill_cost=0.002)
    pricey = _obs("pricey", "z", 12, 24, baseline_cost=0.001, skill_cost=0.05)
    assert cheap.cost_adjusted_value() > pricey.cost_adjusted_value()
    assert cheap.solve_lift() == pricey.solve_lift()    # same raw lift


def test_value_ledger_tracks_decline() -> None:
    lg = SkillValueLedger()
    lg.record(_obs("verify", "s", 10, 25))
    assert not lg.is_declining("verify")
    lg.record(_obs("verify", "s", 10, 14))              # value dropped
    assert lg.is_declining("verify")
    assert lg.current_value("verify") is not None
