"""Benchmark runner aggregates solve rate by difficulty (Alpha 23 WS3)."""

from __future__ import annotations

from types import SimpleNamespace

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.agents.vendor_native import VendorRunResult
from acp.evaluation.benchmark_runner import run_benchmark


class _StubHarness:
    """Solves easy/medium, fails hard, times out one task — exercises every aggregation."""

    spec = SimpleNamespace(name="stub")

    def run_task(self, repo, prompt, *, task_type, task_name, timeout_s,
                 skill_content=None):
        res = VendorRunResult(harness="stub", version="v", task_type=task_type,
                              task_name=task_name)
        if task_name == "roman":          # a conclusive failure
            res.no_patch_solve = False
            res.outcome = "task_failure"
        elif task_name == "merge_intervals":   # an infra timeout (inconclusive)
            res.timed_out = True
            res.outcome = "infra_timeout_before_action"
        else:                              # easy/medium solved
            res.no_patch_solve = True
            res.pytest_passed = True
            res.outcome = "task_success"
        return res


def test_run_benchmark_aggregates_by_difficulty() -> None:
    result = run_benchmark(_StubHarness(), timeout_s=5)
    assert result.harness == "stub"
    assert result.n_attempts == len(BENCH_TASKS)
    # easy (2/2) + medium (2/2) solved, hard has 1 fail + 1 timeout (inconclusive)
    assert result.by_difficulty["easy"]["solve_rate"] == 1.0
    assert result.by_difficulty["medium"]["solve_rate"] == 1.0
    # hard: only the conclusive failure counts; the timeout is dropped from the denominator
    assert result.by_difficulty["hard"]["n_conclusive"] == 1
    assert result.by_difficulty["hard"]["solve_rate"] == 0.0
    # overall: 4 successes / 5 conclusive (the timeout excluded) = 0.8
    assert result.n_conclusive == 5
    assert result.overall_solve_rate == 0.8


def test_skill_flag_recorded() -> None:
    result = run_benchmark(_StubHarness(), skill_content="# skill", timeout_s=5)
    assert result.skill_injected is True
    d = result.to_dict()
    assert d["by_difficulty"] and len(d["tasks"]) == len(BENCH_TASKS)
