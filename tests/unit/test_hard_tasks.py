"""Hard task cohort is real + solvable, proven offline (Alpha 25, test F)."""

from __future__ import annotations

import pytest

from acp.agents.benchmark_suite import apply_reference_fix, build_bench_repo, run_pytest
from acp.agents.hard_tasks import HARD_TASKS


def test_cohort_is_all_hard_and_unique() -> None:
    assert len(HARD_TASKS) >= 5
    assert all(t.difficulty == "hard" for t in HARD_TASKS)
    assert len({t.name for t in HARD_TASKS}) == len(HARD_TASKS)


@pytest.mark.parametrize("task", HARD_TASKS, ids=lambda t: t.name)
def test_greedy_buggy_fails_then_dp_reference_passes(task, tmp_path) -> None:
    repo = build_bench_repo(tmp_path, task)
    assert not run_pytest(repo), f"{task.name}: buggy (greedy) module unexpectedly passed"
    apply_reference_fix(repo, task)
    assert run_pytest(repo), f"{task.name}: reference (DP) fix did not pass"


def test_prompt_does_not_leak_the_fix() -> None:
    for t in HARD_TASKS:
        assert t.fixed not in t.prompt
