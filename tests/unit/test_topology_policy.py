"""Learned topology policy (Alpha 14 WS16)."""

from __future__ import annotations

from acp.routing.topology_policy import (
    TopologyArm,
    recommend_topology,
    should_update_topology_policy,
)


def test_low_risk_skip_reduces_cost_when_success_holds() -> None:
    # On a low-risk docs task, skipping retrieval keeps success and costs less.
    arms = [
        TopologyArm([], success_rate=1.0, cost=0.010, sample_size=5),
        TopologyArm(["skip_retrieval"], success_rate=1.0, cost=0.004, sample_size=5),
    ]
    rec = recommend_topology("docs", "low", arms)
    assert rec.topology == ["skip_retrieval"] and rec.cost_saving == 0.006


def test_skip_rejected_when_it_degrades_success() -> None:
    arms = [
        TopologyArm([], success_rate=1.0, cost=0.010, sample_size=5),
        TopologyArm(["skip_planner"], success_rate=0.80, cost=0.004, sample_size=5),
    ]
    rec = recommend_topology("bugfix", "low", arms)
    assert rec.topology == []  # cheaper arm degrades success -> not chosen


def test_security_never_gets_unsafe_skip_even_if_cheaper() -> None:
    # Evidence says skipping strict verification is cheap + "successful", but the
    # safety gate forbids it for security -> arm ignored, full shape kept.
    arms = [
        TopologyArm([], success_rate=1.0, cost=0.030, sample_size=5),
        TopologyArm(["skip_strict_verification"], success_rate=1.0, cost=0.005,
                    sample_size=5),
    ]
    rec = recommend_topology("security_fix", "high", arms)
    assert rec.topology == []


def test_low_sample_arm_is_not_trusted() -> None:
    arms = [
        TopologyArm([], success_rate=1.0, cost=0.010, sample_size=5),
        TopologyArm(["skip_retrieval"], success_rate=1.0, cost=0.001, sample_size=1),
    ]
    rec = recommend_topology("docs", "low", arms)
    assert rec.topology == []  # 1-sample arm ignored


def test_contaminated_run_skips_policy_update() -> None:
    clean = [{"adapter": "openai_harness", "task_type": "docs", "success": True,
              "status": "succeeded", "tool_calls": 2, "is_harness": True}]
    contaminated = clean + [{"adapter": "openai_harness", "task_type": "docs",
                             "success": False, "status": "timed_out", "timed_out": True,
                             "tool_calls": 0, "error": "timed out", "is_harness": True}
                            for _ in range(4)]
    assert should_update_topology_policy(clean)
    assert not should_update_topology_policy(contaminated)
