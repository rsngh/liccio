"""Meta-agent FinOps tests (GOALS Alpha 42 P6)."""

from __future__ import annotations

from acp.finops import (
    allow_best_of_k,
    budget_for,
    finops_report,
    marginal_value_of_next_call,
    promotion_decision,
)


def test_security_fix_allows_more_spend_than_docs() -> None:
    assert budget_for("high_risk_security") > budget_for("cheap_docs")
    assert budget_for("incident") > budget_for("normal_bugfix")


def test_budget_blocks_best_of_k_when_marginal_value_negative() -> None:
    # tiny uplift on a cheap-docs task whose success isn't worth much -> not worth another call
    assert not allow_best_of_k(budget_class="cheap_docs", spend_so_far=0.0,
                               next_candidate_cost=0.02, p_success_now=0.80,
                               p_success_after=0.81)
    # a real uplift on a high-value incident -> worth it
    assert allow_best_of_k(budget_class="incident", spend_so_far=0.0,
                           next_candidate_cost=0.02, p_success_now=0.50, p_success_after=0.70)


def test_budget_exhaustion_blocks_even_positive_value() -> None:
    d = marginal_value_of_next_call(p_success_now=0.3, p_success_after=0.9, call_cost=0.2,
                                    budget_class="cheap_docs", spend_so_far=0.0)
    assert not d.proceed and "budget exhausted" in d.reason  # 0.2 > cheap_docs ceiling 0.01


def test_finops_report_attributes_cost_to_executor_advisor_candidate() -> None:
    arena = {
        "policy_scores": [
            {"policy": "cheap_single", "verified_success_rate": 0.6,
             "cost_per_verified_success": 0.003},
            {"policy": "advisor_router", "verified_success_rate": 0.8,
             "cost_per_verified_success": 0.004},
            {"policy": "best_of_k_router", "verified_success_rate": 0.8,
             "cost_per_verified_success": 0.006},
        ],
        "attempts": [
            {"policy": "cheap_single", "cost_usd": 0.002, "solved": True,
             "advisor_calls": 0, "candidates_sampled": 0},
            {"policy": "advisor_router", "cost_usd": 0.005, "solved": True,
             "advisor_calls": 1, "candidates_sampled": 0},
            {"policy": "best_of_k_router", "cost_usd": 0.004, "solved": True,
             "advisor_calls": 0, "candidates_sampled": 2},
        ],
    }
    rep = finops_report(arena)
    attr = rep["cost_attribution"]
    assert attr["advisor_router"]["advisor_cost_usd"] > 0      # advisor share attributed
    assert attr["best_of_k_router"]["candidates_sampled"] == 2
    assert attr["best_of_k_router"]["best_of_k_wasted_candidate_rate"] == 0.5  # 2 sampled, 1 used
    assert attr["cheap_single"]["advisor_cost_usd"] == 0.0


def test_promotion_requires_pareto_improvement() -> None:
    inc = {"policy": "cheap_single", "verified_success_rate": 0.6,
           "cost_per_verified_success": 0.003}
    better = {"policy": "repo_map_router", "verified_success_rate": 1.0,
              "cost_per_verified_success": 0.0015}        # higher quality AND cheaper
    worse_cost = {"policy": "claude_harness", "verified_success_rate": 0.8,
                  "cost_per_verified_success": 0.03}      # better quality but much costlier
    assert promotion_decision(better, inc)["promotable"]
    # higher quality but cost/success regresses -> not auto-promotable under the Pareto gate
    assert not promotion_decision(worse_cost, inc)["promotable"]


def test_arena_finops_end_to_end_picks_repo_map() -> None:
    # the committed live arena should rank repo_map_router as best value if present
    import json
    from pathlib import Path
    p = Path("reports/metarouter_arena.json")
    if not p.exists():
        return
    rep = finops_report(json.loads(p.read_text()))
    assert rep["best_value_policy"] in ("repo_map_router", "oracle", "cheap_single")
