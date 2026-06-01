"""Router learns from a multi-harness bakeoff EvalRun (round-4 Block G)."""

from __future__ import annotations

import pytest

from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.replay import (
    PolicyReplayer,
    action_for_adapter,
    observations_from_report,
    replay_context_key,
)


def _cell(task, adapter, *, success, cost, verification_pass=None, reward=None):
    return {"name": f"{task}/{adapter}", "task": task, "adapter": adapter,
            "success": success, "cost_usd": cost,
            "verification_pass": success if verification_pass is None else verification_pass,
            "reward": reward}


def _report(cells):
    return {"mode": "multi_harness_no_patch", "cells": cells}


def _exploit_policy():
    # epsilon=0 -> deterministic exploit of the best learned mean
    return SimulatedBanditPolicy(seed=7, epsilon=0.0)


def test_policy_learns_from_eval_run() -> None:
    policy = _exploit_policy()
    report = _report([_cell("bugfix", "harness", success=True, cost=0.001),
                      _cell("bugfix", "baseline", success=False, cost=0.0)])
    rep = PolicyReplayer(policy).replay(report, run_id="run1")
    assert rep["applied"] and rep["observations"] == 2
    assert rep["preference_changes"], "no arm changes recorded"
    ctx = replay_context_key("bugfix")
    assert ctx in policy.arms
    assert policy.arms[ctx][action_for_adapter("harness").key()].n == 1


def test_policy_prefers_successful_harness_after_replay() -> None:
    policy = _exploit_policy()
    report = _report([_cell("bugfix", "harness", success=True, cost=0.001),
                      _cell("bugfix", "baseline", success=False, cost=0.0)])
    PolicyReplayer(policy).replay(report, run_id="run1")
    candidates = [action_for_adapter("baseline"), action_for_adapter("harness")]
    decision = policy.choose_action({"task_type": "bugfix", "risk_level": "medium"}, candidates)
    assert decision.action.agent_name == "harness"


def test_policy_penalizes_high_cost_equal_quality_agent() -> None:
    policy = _exploit_policy()
    # both solve (equal quality) but one is far more expensive
    report = _report([_cell("bugfix", "cheap", success=True, cost=0.001),
                      _cell("bugfix", "pricey", success=True, cost=0.5)])
    PolicyReplayer(policy).replay(report, run_id="run1")
    ctx = replay_context_key("bugfix")
    cheap_mean = policy.arms[ctx][action_for_adapter("cheap").key()].mean
    pricey_mean = policy.arms[ctx][action_for_adapter("pricey").key()].mean
    assert cheap_mean > pricey_mean
    candidates = [action_for_adapter("pricey"), action_for_adapter("cheap")]
    decision = policy.choose_action({"task_type": "bugfix", "risk_level": "medium"}, candidates)
    assert decision.action.agent_name == "cheap"


def test_policy_replay_idempotent() -> None:
    policy = _exploit_policy()
    report = _report([_cell("bugfix", "harness", success=True, cost=0.001),
                      _cell("feature", "harness", success=True, cost=0.002)])
    replayer = PolicyReplayer(policy)
    first = replayer.replay(report, run_id="runX")
    snapshot = {ctx: {k: s.n for k, s in arms.items()}
                for ctx, arms in policy.arms.items()}
    second = replayer.replay(report, run_id="runX")
    assert first["applied"] is True
    assert second["applied"] is False and second["reason"] == "already_applied"
    after = {ctx: {k: s.n for k, s in arms.items()}
             for ctx, arms in policy.arms.items()}
    assert after == snapshot  # no double counting


def test_observations_carry_cost_penalty() -> None:
    obs = observations_from_report(_report([
        _cell("bugfix", "cheap", success=True, cost=0.0),
        _cell("bugfix", "pricey", success=True, cost=1.0)]))
    by_adapter = {o.action.agent_name: o for o in obs}
    assert by_adapter["cheap"].reward > by_adapter["pricey"].reward


# --- service-level: persisted EvalRun replay, idempotent across restart ------
@pytest.fixture
def service(tmp_path):
    from acp.api.service import AppService
    from acp.core.config import ACPSettings
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'g.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_service_replay_persisted_and_idempotent(service) -> None:
    from acp.api.service import AppService

    # persist a bakeoff EvalRun (deterministic fake+patch baselines)
    run = service.run_multi_harness_bakeoff()
    first = service.replay_bakeoff_into_policy(run.id)
    assert first["applied"] is True
    # a fresh service must see the run as already applied (durable idempotency)
    fresh = AppService(service.settings)
    second = fresh.replay_bakeoff_into_policy(run.id)
    assert second["applied"] is False
