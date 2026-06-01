"""Delayed outcome simulator + post-merge downgrade (round-5 WS8)."""

from __future__ import annotations

import pytest

from acp.evaluation.postmerge_sim import (
    NEGATIVE_OUTCOMES,
    apply_outcomes_to_policy,
    outcomes_summary,
    simulate_outcomes,
)
from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.replay import PolicyReplayer, action_for_adapter


def _cell(adapter, *, success, cost):
    return {"name": f"bugfix/{adapter}", "task": "bugfix", "task_type": "bugfix",
            "adapter": adapter, "success": success, "verification_pass": success,
            "cost_usd": cost, "tool_calls": 3, "tokens": 1000, "latency_s": 1.0,
            "reward": None}


REPORT = {"mode": "multi_harness_v2", "cells": [
    _cell("flashy", success=True, cost=0.0),    # cheap + solves -> day-0 favourite
    _cell("steady", success=True, cost=0.01),   # solves, slightly pricier
]}


def test_simulate_outcomes_only_for_successes() -> None:
    rep = {"cells": [_cell("a", success=True, cost=0.0),
                     _cell("b", success=False, cost=0.0)]}
    outs = simulate_outcomes(rep, seed=1)
    assert {o.adapter for o in outs} == {"a"}  # the failed cell gets no delayed outcome


def test_outcomes_summary_shape() -> None:
    outs = simulate_outcomes(REPORT, revert_profile={"flashy": 1.0, "steady": 0.0}, seed=7)
    s = outcomes_summary(outs)
    assert s["n"] == 2 and "by_kind" in s and 0.0 <= s["negative_rate"] <= 1.0


def test_preferred_harness_downgraded_after_delayed_failures() -> None:
    policy = SimulatedBanditPolicy(seed=5, epsilon=0.0)
    PolicyReplayer(policy).replay(REPORT, run_id="run1")
    cands = [action_for_adapter("flashy"), action_for_adapter("steady")]
    feats = {"task_type": "bugfix", "risk_level": "medium"}
    before = policy.choose_action(feats, cands).action.agent_name
    assert before == "flashy"  # day-0 favourite (cheap + solved)

    # flashy always reverts post-merge; steady is clean
    outcomes = simulate_outcomes(
        REPORT, revert_profile={"flashy": 1.0, "steady": 0.0}, seed=5)
    applied = apply_outcomes_to_policy(policy, outcomes)
    assert applied["negative"] >= 1
    assert any(o.kind in NEGATIVE_OUTCOMES for o in outcomes if o.adapter == "flashy")

    after = policy.choose_action(feats, cands).action.agent_name
    assert after == "steady", "delayed failures did not downgrade the day-0 favourite"


@pytest.fixture
def service(tmp_path):
    from acp.api.service import AppService
    from acp.core.config import ACPSettings
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'pm.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_service_simulate_postmerge_persists(service) -> None:
    run = service.run_multi_harness_bakeoff()  # produces a bakeoff EvalRun
    result = service.simulate_postmerge(run.id, seed=3)
    assert "eval_run_id" in result and "negative_rate" in result
    kinds = [r["kind"] for r in service.list_eval_runs()]
    assert "postmerge_sim" in kinds
