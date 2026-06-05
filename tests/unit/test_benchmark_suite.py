"""Graded benchmark suite is real + solvable, proven offline (Alpha 23 WS2).

Every task must FAIL on its buggy module and PASS once the reference fix is applied — no
vendor call. This guarantees the live benchmark is fair: a harness that fails a task fails
a genuinely-solvable task, and a passing harness solved a genuinely-broken one.
"""

from __future__ import annotations

import pytest

from acp.agents.benchmark_suite import (
    BENCH_TASKS,
    DIFFICULTIES,
    apply_reference_fix,
    build_bench_repo,
    run_pytest,
    tasks_by_difficulty,
)


def test_suite_is_graded() -> None:
    diffs = {t.difficulty for t in BENCH_TASKS}
    assert diffs == set(DIFFICULTIES)  # easy + medium + hard all present
    assert len({t.name for t in BENCH_TASKS}) == len(BENCH_TASKS)  # unique names
    for d in DIFFICULTIES:
        assert tasks_by_difficulty(d), f"no tasks at {d}"


@pytest.mark.parametrize("task", BENCH_TASKS, ids=lambda t: t.name)
def test_buggy_fails_then_reference_fix_passes(task, tmp_path) -> None:
    repo = build_bench_repo(tmp_path, task)
    assert not run_pytest(repo), f"{task.name}: buggy module unexpectedly passed"
    apply_reference_fix(repo, task)
    assert run_pytest(repo), f"{task.name}: reference fix did not pass"


def test_prompt_never_leaks_the_fix() -> None:
    # The harness gets the prompt + buggy source only — never the reference fix.
    for t in BENCH_TASKS:
        assert t.fixed not in t.prompt
        assert t.module_path in t.prompt
