"""Repo-replay realistic bug tasks, proven solvable offline (Alpha 29)."""

from __future__ import annotations

import pytest

from acp.agents.benchmark_suite import apply_reference_fix, build_bench_repo, run_pytest
from acp.agents.repo_replay import REPLAY_TASKS


def test_cohort_has_realistic_tasks() -> None:
    assert len(REPLAY_TASKS) >= 5
    names = {t.name for t in REPLAY_TASKS}
    assert {"semver_compare", "paginate", "deep_merge", "lru_cache"} <= names


@pytest.mark.parametrize("task", REPLAY_TASKS, ids=lambda t: t.name)
def test_buggy_fails_then_reference_fix_passes(task, tmp_path) -> None:
    bench = task.as_bench_task()
    repo = build_bench_repo(tmp_path, bench)
    assert not run_pytest(repo), f"{task.name}: buggy module unexpectedly passed"
    apply_reference_fix(repo, bench)
    assert run_pytest(repo), f"{task.name}: reference fix did not pass"


def test_prompt_carries_issue_not_fix() -> None:
    for t in REPLAY_TASKS:
        bench = t.as_bench_task()
        assert "ISSUE:" in bench.prompt
        assert t.fixed not in bench.prompt        # the fix is never leaked
        assert t.test_src not in bench.prompt      # hidden verifier not shown
