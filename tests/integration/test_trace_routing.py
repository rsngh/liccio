"""Router learning from trace features (round-5 WS7)."""

from __future__ import annotations

from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.replay import (
    PolicyReplayer,
    action_for_adapter,
    observations_from_report,
    replay_context_key,
)
from acp.routing.trace_features import cell_trace_features, summarize_agent_history


def _cell(task_type, adapter, *, success, cost=0.001, tool_calls=3, tokens=1000, latency=1.0,
          human_review=False):
    return {"name": f"{task_type}/{adapter}", "task": task_type, "task_type": task_type,
            "adapter": adapter, "success": success, "cost_usd": cost,
            "verification_pass": success, "tool_calls": tool_calls, "commands": 1,
            "file_writes": ["calculator.py"], "diff_lines": 5, "tokens": tokens,
            "latency_s": latency, "is_harness": True, "reward": None,
            "human_review_required": human_review}


# harness_a wins bugfix; harness_b wins refactor
V2_REPORT = {"mode": "multi_harness_v2", "cells": [
    _cell("bugfix", "harness_a", success=True),
    _cell("bugfix", "harness_b", success=False),
    _cell("refactor", "harness_a", success=False),
    _cell("refactor", "harness_b", success=True),
]}


def test_cell_trace_features_shape() -> None:
    f = cell_trace_features(V2_REPORT["cells"][0])
    assert {"tool_calls", "commands", "file_writes", "diff_lines", "cost_usd",
            "latency_s", "is_harness", "trace_complexity"}.issubset(f)
    assert f["file_writes"] == 1  # list collapsed to count


def test_summarize_agent_history_per_task_type() -> None:
    hist = summarize_agent_history(V2_REPORT)
    assert hist["harness_a"]["bugfix"]["agent_success_by_task_type"] == 1.0
    assert hist["harness_a"]["refactor"]["agent_success_by_task_type"] == 0.0
    assert hist["harness_b"]["refactor"]["agent_success_by_task_type"] == 1.0
    # context efficiency present + finite
    assert "agent_context_efficiency" in hist["harness_a"]["bugfix"]


def test_observations_carry_trace_features_and_provenance() -> None:
    obs = observations_from_report(V2_REPORT, eval_run_id="run42")
    assert all(o.eval_run_id == "run42" for o in obs)
    assert all(o.outcome_source == "bakeoff" for o in obs)
    assert all("trace_complexity" in o.trace_features for o in obs)


def test_replay_changes_preferred_harness_per_task_class() -> None:
    policy = SimulatedBanditPolicy(seed=3, epsilon=0.0)
    PolicyReplayer(policy).replay(V2_REPORT, run_id="run42")
    cands = [action_for_adapter("harness_a"), action_for_adapter("harness_b")]
    bugfix = policy.choose_action(
        {"task_type": "bugfix", "risk_level": "medium"}, cands)
    refactor = policy.choose_action(
        {"task_type": "refactor", "risk_level": "medium"}, cands)
    # the router prefers a DIFFERENT harness depending on task class
    assert bugfix.action.agent_name == "harness_a"
    assert refactor.action.agent_name == "harness_b"
    assert bugfix.action.agent_name != refactor.action.agent_name
    # contexts are task-type-specific
    assert replay_context_key("bugfix") != replay_context_key("refactor")
