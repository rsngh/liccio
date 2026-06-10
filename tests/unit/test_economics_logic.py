# ruff: noqa: E501
"""Lock in the routing-economics analysis math on a tiny deterministic fixture (no reports/network).

These functions produce the project's headline cost numbers; a silent regression here would corrupt
every economics report. Fixture: 2 agents (cheap, exp), 2 bundles — cheap solves b0 only, exp solves both.
"""

from __future__ import annotations

from evals.issue_replay.cost_sensitivity import ORDER, _escalation_cost, _prior
from evals.issue_replay.coverage_scaling import _union_rate
from evals.issue_replay.memory_economics import _per_bundle_costs

SOLVES = {"cheap": [1, 0], "exp": [1, 1]}
ORD = ["cheap", "exp"]
COST = {"cheap": 1.0, "exp": 5.0}


def test_union_rate() -> None:
    assert _union_rate(SOLVES, ("cheap", "exp"), 2) == 1.0     # together cover both
    assert _union_rate(SOLVES, ("cheap",), 2) == 0.5           # cheap covers only b0
    assert _union_rate(SOLVES, ("exp",), 2) == 1.0             # exp covers both (superset)


def test_escalation_cost_pays_failed_cheap_attempt() -> None:
    # b0: cheap solves -> pay 1; b1: cheap fails (1) then exp solves (5) -> 6; total 7, both solved
    total, solved = _escalation_cost(SOLVES, ORD, COST, 2)
    assert total == 7.0 and solved == 2


def test_per_bundle_costs_blind_vs_winner() -> None:
    blind, winner = _per_bundle_costs(SOLVES, ORD, COST, 2)
    assert blind == [1.0, 6.0]      # b1 blind pays cheap+exp
    assert winner == [1.0, 5.0]     # memory recurrence pays only the winning rung


def test_unsolved_bundle_has_zero_winner_cost() -> None:
    # neither agent solves b1 -> blind pays the full ladder, winner cost 0 (nothing to re-pay)
    solves = {"cheap": [1, 0], "exp": [1, 0]}
    blind, winner = _per_bundle_costs(solves, ORD, COST, 2)
    assert blind == [1.0, 6.0] and winner == [1.0, 0.0]


def test_prior_is_monotone_increasing_with_correct_endpoints() -> None:
    p = _prior(8.0)
    vals = [p[a] for a in ORDER]
    assert vals[0] == 1.0 and abs(vals[-1] - 8.0) < 1e-9        # cheap=1, strongest=m
    assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))  # strictly increasing
    assert _prior(1.0) == dict.fromkeys(ORDER, 1.0)            # m=1 -> flat
