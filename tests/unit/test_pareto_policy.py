"""Pareto routing policy + multi-objective profiles (Alpha 9, WS2/WS3)."""

from __future__ import annotations

from acp.core.enums import AgentKind
from acp.routing.pareto_policy import PROFILES, ParetoRoutingPolicy
from acp.routing.policy import RoutingPolicy
from acp.schemas.routing import RoutingAction


def _candidates() -> list[RoutingAction]:
    return [
        RoutingAction(agent_kind=AgentKind.CLAUDE, agent_name="claude_harness",
                      context_strategy="test_focused", max_cost_usd=2.0),
        RoutingAction(agent_kind=AgentKind.FAKE, agent_name="fake",
                      context_strategy="minimal", max_cost_usd=0.1),
    ]


def _features():
    return {"task_type": "bugfix", "risk_level": "medium"}


def test_implements_routing_policy_protocol() -> None:
    assert isinstance(ParetoRoutingPolicy(), RoutingPolicy)


def test_all_six_profiles_exist() -> None:
    assert set(PROFILES) == {"cost_saver", "balanced", "success_max", "risk_min",
                             "latency_min", "human_review_min"}


def test_profiles_pick_differently() -> None:
    cands = _candidates()
    cost = ParetoRoutingPolicy(profile=PROFILES["cost_saver"]).choose_action(
        _features(), cands)
    success = ParetoRoutingPolicy(profile=PROFILES["success_max"]).choose_action(
        _features(), cands)
    # Cost-saver prefers the cheap agent; success-max prefers the harness.
    assert cost.action.agent_name == "fake"
    assert success.action.agent_name == "claude_harness"
    assert "pareto" in cost.exploration_reason


def test_decision_carries_frontier_explanation() -> None:
    dec = ParetoRoutingPolicy().choose_action(_features(), _candidates())
    assert dec.candidate_scores
    assert 0.0 < dec.action_probability <= 1.0
    assert dec.policy_version.startswith("pareto-")


def test_risk_min_profile_filters_high_risk_context() -> None:
    # risk_min disallows high/critical risk contexts -> falls back but still chooses.
    pol = ParetoRoutingPolicy(profile=PROFILES["risk_min"])
    dec = pol.choose_action({"task_type": "security_fix", "risk_level": "high"},
                            _candidates())
    assert dec.action is not None
