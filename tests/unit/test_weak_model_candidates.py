"""Weak-model best-of-k candidate generation + execution comparator (Alpha 24 area 2)."""

from __future__ import annotations

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.agents.weak_model_candidates import (
    CandidatePatch,
    best_of_k,
    cost_usd,
    select_best,
    verify_candidate,
)

DIVIDE = next(t for t in BENCH_TASKS if t.name == "divide")


def _stub(contents):
    # sampler returning a fixed sequence of module contents (None = API error)
    def _s(task, i):
        c = contents[i]
        return CandidatePatch(index=i, content=c, in_tokens=100, out_tokens=50,
                              cost=cost_usd("gpt-4o-mini", 100, 50))
    return _s


def test_passing_candidate_is_verified_by_execution() -> None:
    v = verify_candidate(DIVIDE, CandidatePatch(index=0, content=DIVIDE.fixed))
    assert v.applied and v.pytest_passed and v.conclusive
    v2 = verify_candidate(DIVIDE, CandidatePatch(index=1, content=DIVIDE.buggy))
    assert v2.conclusive and not v2.pytest_passed  # buggy candidate fails honestly


def test_best_of_k_selects_passing_with_minimal_diff() -> None:
    # 3 candidates: buggy (fails), a verbose fix, the minimal fix -> pick minimal.
    verbose = DIVIDE.fixed + "\n# extra\n# noise\n"
    res = best_of_k(DIVIDE, k=3, sampler=_stub([DIVIDE.buggy, verbose, DIVIDE.fixed]))
    assert res.solved and res.n_passed == 2 and res.n_conclusive == 3
    assert res.best_index == 2  # minimal diff among the two passing
    assert res.outcome == "task_success"
    assert res.diversity == 1.0  # all three distinct


def test_all_api_errors_are_inconclusive_not_failure() -> None:
    res = best_of_k(DIVIDE, k=2, sampler=_stub([None, None]))
    assert res.n_conclusive == 0 and not res.solved
    assert res.outcome == "infra_timeout_before_action"  # infra, never task_failure


def test_select_best_returns_none_when_nothing_passes() -> None:
    res = best_of_k(DIVIDE, k=2, sampler=_stub([DIVIDE.buggy, DIVIDE.buggy]))
    assert res.best_index is None and res.outcome == "task_failure"
    assert select_best(res.candidates) is None


def test_cost_accumulates() -> None:
    res = best_of_k(DIVIDE, k=4, sampler=_stub([DIVIDE.fixed] * 4))
    assert res.total_cost > 0 and res.k == 4
    assert res.diversity == 0.25  # all identical -> 1 distinct / 4
