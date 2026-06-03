"""Pareto live config (WS2) + production policy pack (WS19)."""

from __future__ import annotations

import pytest

from acp.core.enums import AgentKind
from acp.core.pareto_config import ParetoRoutingConfig
from acp.core.policy_pack import POLICY_PACK, enforce
from acp.routing.pareto_policy import ParetoRoutingPolicy
from acp.schemas.routing import RoutingAction


# ---- WS2 -----------------------------------------------------------------
def test_default_map_routes_task_types() -> None:
    cfg = ParetoRoutingConfig()
    assert cfg.profile_name("docs") == "cost_saver"
    assert cfg.profile_name("bugfix") == "balanced"
    assert cfg.profile_name("ci_fix") == "latency_min"
    assert cfg.profile_name("security_fix") == "risk_min"


def test_high_risk_safety_override() -> None:
    cfg = ParetoRoutingConfig()
    # Even a cost_saver task type is forced to risk_min at high risk.
    assert cfg.profile_name("docs", "high") == "risk_min"
    assert cfg.profile_name("bugfix", "critical") == "risk_min"


def test_from_dict_validates_profiles() -> None:
    cfg = ParetoRoutingConfig.from_dict({"profiles": {"incident": "success_max"}})
    assert cfg.profile_name("incident") == "success_max"
    with pytest.raises(ValueError):
        ParetoRoutingConfig.from_dict({"profiles": {"x": "not_a_profile"}})


def test_resolved_profile_drives_pareto_choice() -> None:
    cfg = ParetoRoutingConfig()
    cands = [
        RoutingAction(agent_kind=AgentKind.CLAUDE, agent_name="claude_harness",
                      context_strategy="test_focused", max_cost_usd=2.0),
        RoutingAction(agent_kind=AgentKind.FAKE, agent_name="fake",
                      context_strategy="minimal", max_cost_usd=0.1),
    ]
    docs = ParetoRoutingPolicy(profile=cfg.resolve("docs")).choose_action(
        {"task_type": "docs", "risk_level": "low"}, cands)
    incident = ParetoRoutingPolicy(profile=cfg.resolve("incident")).choose_action(
        {"task_type": "incident", "risk_level": "low"}, cands)
    assert docs.action.agent_name == "fake"            # cost_saver
    assert incident.action.agent_name == "claude_harness"  # success_max


# ---- WS19 ----------------------------------------------------------------
def test_policy_pack_has_three_modes() -> None:
    assert set(POLICY_PACK) == {"lab", "staging", "production"}
    assert POLICY_PACK["production"].require_docker_live_gate is True
    assert POLICY_PACK["lab"].allow_local_true_harness is True
    assert POLICY_PACK["production"].allow_local_true_harness is False


def test_enforce_production_blocks_on_missing_gates() -> None:
    health = {"production_gates": {"artifact_manifest_valid": True,
                                   "docker_live_security_passed": False,
                                   "ope_overlap_sufficient": False,
                                   "test_reports_present": True}}
    res = enforce("production", health)
    assert res.satisfied is False
    assert "docker_live_security_passed" in res.failed_requirements


def test_enforce_lab_is_lenient() -> None:
    health = {"production_gates": {"artifact_manifest_valid": True,
                                   "docker_live_security_passed": False,
                                   "ope_overlap_sufficient": False,
                                   "test_reports_present": False}}
    res = enforce("lab", health)
    assert res.satisfied is True  # lab requires only a valid manifest
