# ruff: noqa: E501, C408
"""Unified router — offline tests (fake attempt_fn; no network): escalation, memory, finops, safety."""

from __future__ import annotations

from acp.memory.experience_bank import ExperienceBank
from acp.memory.memory_policy import MemoryPolicy
from acp.routing.topology_program_executor import AttemptOutcome
from acp.routing.unified_router import Lever, route_and_solve

LADDER = [
    Lever("haiku_minimal", est_cost=0.002, prior_p_solve=0.5),
    Lever("haiku_repomap", est_cost=0.003, prior_p_solve=0.7),
    Lever("sonnet_repomap", est_cost=0.006, prior_p_solve=0.8),
    Lever("opus_repomap", est_cost=0.03, prior_p_solve=0.9),
]


def _fake_fn(solve_map, cost_map=None, forbidden=()):
    cost_map = cost_map or {}

    def fn(action, _task_id):
        if action not in {lev.name for lev in LADDER}:
            return None
        return AttemptOutcome(solved=solve_map.get(action, False), public_solved=solve_map.get(action, False),
                              cost=cost_map.get(action, 0.001), touched_forbidden=action in forbidden)
    return fn


def test_escalates_until_solved() -> None:
    # cheap rung fails, repo_map solves -> path shows escalation, solved
    res = route_and_solve(task_id="t", failure_signature="bugfix:cross_file_api", repo_family="r",
                          tenant="t", task_type="bugfix", risk_level="low", budget_class="normal_bugfix",
                          ladder=LADDER, attempt_fn=_fake_fn({"haiku_repomap": True}), memory=None)
    assert res.solved and res.terminal == "commit_success"
    assert res.lever_path[:2] == ["haiku_minimal", "haiku_repomap"]


def test_memory_skips_known_bad_rung_next_session() -> None:
    mem = ExperienceBank()
    pol = MemoryPolicy()
    fn = _fake_fn({"haiku_repomap": True}, cost_map={"haiku_minimal": 0.002, "haiku_repomap": 0.003})
    common = dict(task_id="t", failure_signature="bugfix:cross_file_api", repo_family="r", tenant="t",
                  task_type="bugfix", risk_level="low", budget_class="normal_bugfix", ladder=LADDER,
                  attempt_fn=fn, memory=mem, memory_policy=pol)
    s0 = route_and_solve(**common, now=0.0)
    s1 = route_and_solve(**common, now=1.0)
    # session 0 paid for the failing cheap rung; session 1 skips it (memory learned to avoid it)
    assert "haiku_minimal" in s0.lever_path
    assert "haiku_minimal" not in s1.ladder_used and s1.used_memory_seed
    assert s1.total_cost < s0.total_cost and s1.solved


def test_finops_trims_unaffordable_rungs() -> None:
    # cheap_docs budget ($0.01) cannot afford the $0.03 opus rung -> trimmed from the ladder
    res = route_and_solve(task_id="t", failure_signature="docs:none", repo_family="r", tenant="t",
                          task_type="bugfix", risk_level="low", budget_class="cheap_docs",
                          ladder=LADDER, attempt_fn=_fake_fn({}), memory=None)
    assert "opus_repomap" not in res.ladder_used


def test_safety_forbidden_file_never_commits() -> None:
    # a rung that "solves" but touched a forbidden file must not be committed
    res = route_and_solve(task_id="t", failure_signature="sec:none", repo_family="r", tenant="t",
                          task_type="security_fix", risk_level="low", budget_class="normal_bugfix",
                          ladder=LADDER, attempt_fn=_fake_fn({"haiku_minimal": True}, forbidden={"haiku_minimal"}),
                          memory=None)
    assert not res.solved
    assert any("forbidden" in note for note in res.safety_notes)


def test_high_risk_unsolved_routes_to_human() -> None:
    res = route_and_solve(task_id="t", failure_signature="sec:none", repo_family="r", tenant="t",
                          task_type="security_fix", risk_level="high", budget_class="high_risk_security",
                          ladder=LADDER, attempt_fn=_fake_fn({}), memory=None)
    assert res.terminal == "route_to_human" and not res.solved
