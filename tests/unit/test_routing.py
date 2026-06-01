"""Routing, bandit, OPE, registry, reward tests (charter §13, §16)."""

from __future__ import annotations

import pytest

from acp.core.enums import PolicyStatus, RiskLevel, TaskType
from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.constraints import apply_constraints
from acp.routing.heuristic import HeuristicRouter
from acp.routing.off_policy import OffPolicyError
from acp.routing.off_policy import evaluate as ope_evaluate
from acp.routing.policy import PolicyDecision
from acp.routing.registry import PolicyRegistry
from acp.routing.reward import compute_reward
from acp.routing.simulation import make_decision_log, run_simulation
from acp.schemas.agent import AgentAttempt
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.learning import PolicyVersion, RewardEvent
from acp.schemas.routing import RoutingAction
from acp.schemas.task import Task, TaskClassification


def _cls(task_type, risk) -> TaskClassification:
    return TaskClassification(task_type=task_type, risk_level=risk, ambiguity_score=0.2,
                              testability_score=0.8)


def test_heuristic_docs_picks_cheap_route() -> None:
    router = HeuristicRouter(available_agents=["patch", "fake"])
    task = Task(repo_id="r", title="Update docs", body="fix README.md")
    d = router.decide(task, _cls(TaskType.DOCS, RiskLevel.LOW))
    assert d.action.context_strategy == "minimal"
    assert d.action_probability > 0


def test_heuristic_auth_strict_and_human() -> None:
    router = HeuristicRouter(available_agents=["patch", "fake"])
    task = Task(repo_id="r", title="Change auth", body="password hashing")
    d = router.decide(task, _cls(TaskType.FEATURE, RiskLevel.HIGH))
    assert d.action.verification_policy == "strict"
    assert d.action.requires_human_approval is True
    assert "high_risk_requires_human_review" in d.constraints_applied


def test_constraints_filter_unavailable_and_clamp() -> None:
    cands = [
        RoutingAction(agent_kind="claude", agent_name="claude", max_cost_usd=100, parallelism=10),
        RoutingAction(agent_kind="fake", agent_name="fake"),
    ]
    out, applied = apply_constraints(cands, RiskLevel.HIGH, {"fake"}, max_cost_usd=5.0)
    assert len(out) == 1
    assert out[0].agent_name == "fake"
    assert out[0].requires_human_approval is True


def test_bandit_beats_random_stationary() -> None:
    res = run_simulation(rounds=1500, seed=7)
    assert res.beats_random
    assert res.policy_reward > res.random_reward


def test_bandit_converges_to_strong_arm_on_security() -> None:
    policy = SimulatedBanditPolicy(seed=3, epsilon=0.1)
    run_simulation(policy=policy, rounds=2000, seed=3)
    # arm B should dominate security context
    sec = policy.arms.get("security|medium", {})
    assert sec
    best = max(sec.items(), key=lambda kv: kv[1].mean)[0]
    assert "B" in best


def test_bandit_adapts_under_drift() -> None:
    res = run_simulation(rounds=2000, seed=11, drift_at=1000)
    assert res.beats_random


def test_ope_rejects_missing_propensity() -> None:
    action = RoutingAction(agent_kind="fake", agent_name="A")
    bad = PolicyDecision(policy_version="v", action=action, action_probability=0.5)
    bad.action_probability = 0.5
    log = [(bad, RewardEvent(task_id="t", reward=1.0, components={"x": 1.0}))]
    object.__setattr__(bad, "action_probability", 0.0)  # corrupt propensity
    with pytest.raises(OffPolicyError):
        ope_evaluate(log, lambda d: 0.5)


def test_ope_runs_on_valid_log() -> None:
    log = make_decision_log(seed=5, rounds=100)
    result = ope_evaluate(log, lambda d: 1.0 / 3)
    assert result.n == 100
    assert isinstance(result.ips, float)


def test_policy_registry_promote_and_rollback() -> None:
    reg = PolicyRegistry()
    champ = reg.register(PolicyVersion(name="p", version="1", status=PolicyStatus.CHAMPION.value))
    chall = reg.register(PolicyVersion(name="p", version="2"))
    reg.promote(chall.id, traffic_fraction=0.2)
    assert reg.challenger().id == chall.id
    # full rollback restores v1
    back = reg.rollback(champ.id)
    assert back.id == champ.id
    assert reg.champion().id == champ.id


def test_reward_components_stored() -> None:
    ev = EvaluationResult(task_id="t", spec_compliance=1.0, test_adequacy=1.0)
    att = AgentAttempt(task_id="t", agent_kind="fake", agent_name="fake", estimated_cost_usd=0.1)
    r = compute_reward(ev, att, task_success=True)
    assert r.components
    assert r.components["task_success"] == 3.0
    assert abs(r.reward - sum(r.components.values())) < 1e-6


def test_delayed_revert_lowers_reward() -> None:
    ev = EvaluationResult(task_id="t", spec_compliance=1.0)
    att = AgentAttempt(task_id="t", agent_kind="fake", agent_name="fake")
    good = compute_reward(ev, att, task_success=True)
    reverted = compute_reward(ev, att, task_success=True, reverted_or_incident=True)
    assert reverted.reward < good.reward
