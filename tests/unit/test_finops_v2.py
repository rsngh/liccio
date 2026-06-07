"""FinOps v2 — marginal-value controller + provider market (GOALS Alpha 43 P7)."""

from __future__ import annotations

from acp.finops.marginal_value_controller import (
    MarginalValueController,
    feasible_provider_set,
    provider_market,
)


def test_controller_stops_when_marginal_value_negative() -> None:
    c = MarginalValueController(budget_class="normal_bugfix")
    assert c.should_spend(p_now=0.4, p_after=0.7, step_cost=0.002, label="candidate_1")
    # tiny uplift -> stop spending
    assert not c.should_spend(p_now=0.70, p_after=0.705, step_cost=0.01, label="candidate_2")
    rep = c.report()
    assert rep["n_proceeded"] == 1


def test_controller_respects_budget_class() -> None:
    docs = MarginalValueController(budget_class="cheap_docs")
    # an expensive step on a low-value docs task is refused
    assert not docs.should_spend(p_now=0.5, p_after=0.6, step_cost=0.2, label="expensive")


def test_feasible_excludes_unavailable_and_underevidenced() -> None:
    providers = [
        {"provider": "anthropic", "available": True, "contract_passed": True,
         "conclusive_cells": 50, "verified_success_rate": 0.9, "cost_per_verified_success": 0.01},
        {"provider": "openai", "available": False, "reason": "key missing",
         "conclusive_cells": 0},
        {"provider": "gemini", "available": True, "conclusive_cells": 3},  # too few cells
    ]
    feasible = feasible_provider_set(providers)
    assert feasible == ["anthropic"]
    mkt = provider_market(providers)
    assert mkt["best_value_provider"] == "anthropic"
    assert "openai" in mkt["potential_savings_not_measured"]
    assert "gemini" in mkt["potential_savings_not_measured"]


def test_provider_market_never_ranks_unavailable() -> None:
    providers = [{"provider": "openai", "available": False, "reason": "unavailable",
                  "conclusive_cells": 0}]
    mkt = provider_market(providers)
    assert mkt["ranking"] == [] and mkt["best_value_provider"] is None
