# ruff: noqa: E501
"""Increment-1 lever matrix — offline tests (no network): matrix shape, availability gating, DeepConf."""

from __future__ import annotations

from evals.harness_router.run import _CFG, LEVERS, _attempt_fn

from acp.evaluation.comparator_strength import Candidate, deepconf_select


def test_lever_matrix_spans_four_dimensions() -> None:
    # model levers carry (tier, thinking_budget, context); at least one thinking rung and one cli per family
    kinds = {name: cfg[0] for name, cfg in _CFG.items()}
    assert kinds["gflash_lite_min"] == "model" and kinds["gemini_cli"] == "cli"
    thinking_levers = [n for n, (k, p) in _CFG.items() if k == "model" and p[1]]
    assert thinking_levers, "must have at least one explicit thinking-level lever"
    cli_levers = [n for n, (k, _p) in _CFG.items() if k == "cli"]
    assert {"gemini_cli", "openhands", "codex_cli", "claude_code"} <= set(cli_levers)


def test_ladder_is_cheapest_first() -> None:
    costs = [lev.est_cost for lev in LEVERS]
    # the very first rung is the globally cheapest; opus sits near the end
    assert costs[0] == min(costs)
    assert LEVERS[0].name == "gflash_lite_min"


def test_unavailable_cli_lever_is_skipped_not_faked() -> None:
    # attempt_fn must return None (router skips) for a cli lever marked unavailable
    fn = _attempt_fn(_DummySpec(), None, gemini_key=None, harness_adapter=None,
                     avail={"gemini_cli": False, "openhands": False, "codex_cli": False, "claude_code": False})
    assert fn("codex_cli", "t") is None
    assert fn("unknown_action", "t") is None


def test_deepconf_prunes_low_confidence_before_verification() -> None:
    cands = [Candidate("a", public_pass=True, hidden_pass=False, diff_lines=2, proxy_pass=False),
             Candidate("b", public_pass=True, hidden_pass=True, diff_lines=5, proxy_pass=True),
             Candidate("c", public_pass=False, hidden_pass=False, diff_lines=9, proxy_pass=False)]
    res, savings = deepconf_select(cands, [0.9, 0.8, 0.05], threshold=0.5)
    assert savings["pruned_before_verify"] >= 1      # the low-confidence candidate is pruned
    assert res.selected == "b" and res.selected_verified


class _DummySpec:
    name = "t"
    task_type = "bugfix"
    context_need = "none"
    risk_level = "low"
