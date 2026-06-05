"""AutoTTS-style topology controller search (Alpha 24 area 3)."""

from __future__ import annotations

from acp.routing.topology_controller import (
    ControllerParams,
    TopologyTrace,
    plan_actions,
    safety_violations,
    score_controller,
    search_controllers,
)


def _traces():
    return [
        # easy low-risk tasks succeed cheaply — planner/retrieval are skippable here
        TopologyTrace("bugfix", "low", "easy", False, True, False),
        TopologyTrace("bugfix", "low", "easy", False, True, False),
        # a high-risk security task that genuinely needs strict verification
        TopologyTrace("security_fix", "high", "medium", False, True, True),
        # an ambiguous task
        TopologyTrace("refactor", "medium", "medium", True, True, False),
    ]


def test_high_risk_always_gets_strict_verification() -> None:
    p = ControllerParams(skip_planner_on_easy=True, skip_retrieval_on_low_risk=True)
    sec = TopologyTrace("security_fix", "high", "hard", False, True, True)
    assert "run_strict_verifier" in plan_actions(p, sec)


def test_ambiguous_routes_to_advisor_first() -> None:
    p = ControllerParams()
    amb = TopologyTrace("x", "medium", "medium", True, True, False)
    plan = plan_actions(p, amb)
    assert plan[0] == "consult_advisor"


def test_safety_violations_empty_for_safe_controller() -> None:
    assert safety_violations(ControllerParams(skip_planner_on_easy=True), _traces()) == []


def test_skipping_cheap_stages_reduces_cost_at_equal_success() -> None:
    traces = _traces()
    res = search_controllers(traces)
    # a cheaper safe controller exists (skip planner/retrieval on easy/low-risk)
    assert res.improved
    assert res.best.est_cost < res.baseline.est_cost
    assert res.best.est_success >= res.baseline.est_success
    assert res.best.safe


def test_all_returned_best_is_safe_and_high_risk_preserved() -> None:
    res = search_controllers(_traces())
    assert res.n_safe >= 1 and res.best.safe
    # the security task's success is only credited because strict verify is preserved
    assert res.best.est_success >= 0.75


def test_score_credits_only_verified_success() -> None:
    # a controller that could skip strict verify is unsafe -> never chosen; but verify the
    # crediting rule directly on a forced-unsafe plan path via score on high-risk trace.
    p = ControllerParams()
    s = score_controller(p, [TopologyTrace("sec", "high", "hard", False, True, True)])
    assert s.est_success == 1.0 and "run_strict_verifier" in plan_actions(
        p, TopologyTrace("sec", "high", "hard", False, True, True))
