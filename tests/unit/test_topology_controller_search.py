"""Offline topology-controller-search tests (GOALS Alpha 42 P3)."""

from __future__ import annotations

from acp.routing.topology_controller_search import ControllerCell, TopologyControllerSearch


def _c(need, action, solved, cost=0.002, risk="low", avail=True, conclusive=True):
    return ControllerCell(context_need=need, risk_level=risk, provider_available=avail,
                          action=action, solved=solved, cost=cost, conclusive=conclusive)


def test_controller_picks_best_action_per_context_need() -> None:
    cells = [
        _c("cross_file_api", "cheap_single", False),
        _c("cross_file_api", "cheap_single", False),
        _c("cross_file_api", "retry_with_repo_map", True),
        _c("cross_file_api", "retry_with_repo_map", True),
        _c("none", "cheap_single", True),
        _c("none", "retry_with_repo_map", True, cost=0.01),  # solves but pricier
    ]
    ctrl = TopologyControllerSearch().fit(cells).controller()
    assert ctrl["cross_file_api"] == "retry_with_repo_map"
    assert ctrl["none"] == "cheap_single"   # equal success, cheaper -> better objective


def test_offline_eval_replays_without_live_calls() -> None:
    cells = [_c("none", "cheap_single", True), _c("none", "retry_with_repo_map", True, cost=0.01)]
    res = TopologyControllerSearch().fit(cells).evaluate_offline(cells)
    assert res["replayed_without_live_calls"] is True
    assert res["n_cells"] == 2


def test_unavailable_provider_actions_never_selected() -> None:
    cells = [
        _c("none", "cheap_single", True),
        _c("none", "strong_single", False, avail=False),   # provider unavailable -> excluded
    ]
    s = TopologyControllerSearch().fit(cells)
    assert s.controller()["none"] == "cheap_single"
    rep = s.to_report(cells)
    assert "strong_single" in rep["offline_eval"]["provider_unavailable_actions_never_selected"]


def test_inconclusive_cells_excluded_from_controller() -> None:
    cells = [
        _c("none", "cheap_single", True, conclusive=False),  # contaminated -> ignored
        _c("none", "retry_with_repo_map", True),
    ]
    assert TopologyControllerSearch().fit(cells).controller()["none"] == "retry_with_repo_map"


def test_promotable_only_with_gain() -> None:
    # repo_map dominates cheap on cross-file -> controller should beat the static cheap baseline
    cells = [
        _c("cross_file_api", "cheap_single", False),
        _c("cross_file_api", "retry_with_repo_map", True),
    ]
    rep = TopologyControllerSearch().fit(cells).to_report(cells)
    assert rep["promotable"] == (rep["controller_gain_over_static_baseline"] > 0)
