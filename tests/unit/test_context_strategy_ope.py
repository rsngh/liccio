"""Context-strategy OPE tests (GOALS Alpha 42 P4)."""

from __future__ import annotations

from acp.context.context_strategy_ope import ContextStrategyOPE


def _cell(need, strat, solved, cost=0.002, conclusive=True):
    return {"context_need": need, "strategy": strat, "solved": solved, "cost_usd": cost,
            "conclusive": conclusive}


def test_context_strategy_ope_routes_cross_file_to_repo_map() -> None:
    cells = [
        _cell("cross_file_api", "minimal", False),
        _cell("cross_file_api", "minimal", False),
        _cell("cross_file_api", "repo_map", True),
        _cell("cross_file_api", "repo_map", True),
    ]
    rec = ContextStrategyOPE().fit(cells).recommend("cross_file_api")
    assert rec["recommended"] == "repo_map"
    assert rec["solve_rate"] == 1.0


def test_context_strategy_ope_routes_exact_symbol_to_grep() -> None:
    cells = [
        _cell("exact_symbol", "grep", True, cost=0.0005),
        _cell("exact_symbol", "grep", True, cost=0.0005),
        _cell("exact_symbol", "embedding", True, cost=0.01),   # also solves but pricier
        _cell("exact_symbol", "embedding", False, cost=0.01),
    ]
    rec = ContextStrategyOPE().fit(cells).recommend("exact_symbol")
    assert rec["recommended"] == "grep"   # higher solve rate AND cheaper


def test_cheaper_strategy_wins_when_success_ties() -> None:
    cells = [
        _cell("none", "minimal", True, cost=0.001),
        _cell("none", "repo_map", True, cost=0.005),
    ]
    rec = ContextStrategyOPE().fit(cells).recommend("none")
    assert rec["recommended"] == "minimal"  # equal success -> cheaper value-per-dollar wins


def test_inconclusive_cells_excluded() -> None:
    cells = [_cell("none", "minimal", False, conclusive=False),
             _cell("none", "minimal", True, conclusive=True)]
    est = ContextStrategyOPE().fit(cells).estimate("none", "minimal")
    assert est.n == 1 and est.solve_rate == 1.0   # the inconclusive row is not counted


def test_grep_vs_embedding_reports_null_honestly() -> None:
    ope = ContextStrategyOPE().fit([_cell("none", "minimal", True)])
    assert ope.grep_vs_embedding()["verdict"] == "insufficient_evidence"
    ope2 = ContextStrategyOPE().fit([
        _cell("exact_symbol", "grep", True), _cell("exact_symbol", "grep", True),
        _cell("exact_symbol", "embedding", False)])
    assert ope2.grep_vs_embedding()["verdict"] == "grep_wins"
