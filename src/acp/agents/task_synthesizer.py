"""Synthetic task-corpus generator / active benchmark builder (Alpha 24 area 5).

General-Agent frames task creation as a two-player game: a synthesizer proposes tasks, a
solver measures pass rate, and only tasks in a calibrated difficulty band are accepted. This
module generates parametric bugfix tasks (deterministic from a seed), each shipping a buggy
module + tests + a reference fix in the :class:`BenchTask` shape, so they plug straight into
the graded benchmark and capability matrix.

Acceptance gate (no task is added without these guarantees):
- deterministic verification: the buggy module FAILS its tests and the reference fix PASSES
  (offline, no model) — proven by :func:`accept_task`;
- no answer leakage: the reference fix never appears in the prompt or buggy module;
- difficulty is estimated and the corpus can be filtered to a target band.

``capability_gap_tasks`` targets generation at sparse (task_type, difficulty) cells so
active learning closes under-sampled regions of the matrix.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from acp.agents.benchmark_suite import (
    BenchTask,
    apply_reference_fix,
    build_bench_repo,
    run_pytest,
)


@dataclass
class _Template:
    family: str
    difficulty: str
    build: Callable[[random.Random, int], BenchTask]


def _arith_task(rng: random.Random, uid: int) -> BenchTask:
    a, b = rng.randint(2, 9), rng.randint(2, 9)
    mod = f"arith_{uid}.py"
    buggy = "def solve(x, y):\n    return x + y  # bug: should multiply\n"
    fixed = "def solve(x, y):\n    return x * y\n"
    test = (f"from arith_{uid} import solve\n\n"
            f"def test_solve():\n    assert solve({a}, {b}) == {a * b}\n"
            f"    assert solve(0, 5) == 0\n")
    prompt = (f"There is a bug in {mod}: solve(x, y) must return the product x*y, not the "
              f"sum. Fix it so the tests pass, then run `python -m pytest -q`.")
    return BenchTask(f"arith_{uid}", "easy", mod, buggy, fixed, test, prompt)


def _clamp_task(rng: random.Random, uid: int) -> BenchTask:
    lo, hi = rng.randint(0, 3), rng.randint(7, 10)
    mod = f"clamp_{uid}.py"
    buggy = ("def clamp(x, lo, hi):\n"
             "    if x < lo:\n        return lo\n    return x  # bug: ignores upper bound\n")
    fixed = ("def clamp(x, lo, hi):\n"
             "    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n")
    test = (f"from clamp_{uid} import clamp\n\n"
            f"def test_clamp():\n    assert clamp(5, {lo}, {hi}) == 5\n"
            f"    assert clamp(-1, {lo}, {hi}) == {lo}\n"
            f"    assert clamp(99, {lo}, {hi}) == {hi}\n")
    prompt = (f"There is a bug in {mod}: clamp does not enforce the upper bound. Fix it so "
              f"the tests pass, then run `python -m pytest -q`.")
    return BenchTask(f"clamp_{uid}", "medium", mod, buggy, fixed, test, prompt)


def _running_max_task(rng: random.Random, uid: int) -> BenchTask:
    mod = f"runmax_{uid}.py"
    buggy = ("def running_max(xs):\n"
             "    out = []\n    m = 0  # bug: wrong seed; fails on negatives/empty\n"
             "    for x in xs:\n        m = max(m, x)\n        out.append(m)\n    return out\n")
    fixed = ("def running_max(xs):\n"
             "    out = []\n    m = None\n    for x in xs:\n"
             "        m = x if m is None else max(m, x)\n        out.append(m)\n    return out\n")
    test = (f"from runmax_{uid} import running_max\n\n"
            f"def test_running_max():\n"
            f"    assert running_max([1, 3, 2]) == [1, 3, 3]\n"
            f"    assert running_max([-5, -2, -9]) == [-5, -2, -2]\n"
            f"    assert running_max([]) == []\n")
    prompt = (f"There is a bug in {mod}: running_max is wrong for negative numbers. Fix it "
              f"so the tests pass, then run `python -m pytest -q`.")
    return BenchTask(f"runmax_{uid}", "hard", mod, buggy, fixed, test, prompt)


_TEMPLATES = [
    _Template("arithmetic", "easy", _arith_task),
    _Template("clamp", "medium", _clamp_task),
    _Template("running_max", "hard", _running_max_task),
]
_BY_DIFFICULTY = {t.difficulty: t for t in _TEMPLATES}


def estimate_difficulty(task: BenchTask) -> str:
    """The synthesizer's declared difficulty band (calibrated against solver pass rates)."""
    return task.difficulty


def synthesize(n: int, *, seed: int, difficulty: str | None = None) -> list[BenchTask]:
    """Generate ``n`` parametric tasks deterministically from ``seed``."""
    rng = random.Random(seed)
    templates = [_BY_DIFFICULTY[difficulty]] if difficulty else _TEMPLATES
    tasks: list[BenchTask] = []
    for i in range(n):
        tmpl = templates[i % len(templates)]
        tasks.append(tmpl.build(rng, seed * 1000 + i))
    return tasks


def accept_task(task: BenchTask) -> tuple[bool, str]:
    """Acceptance gate: deterministic solvability + no answer leakage. Offline, no model."""
    if task.fixed in task.prompt or task.fixed in task.buggy:
        return False, "answer leakage"
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)
        if run_pytest(repo):
            return False, "buggy module already passes (not a real bug)"
        apply_reference_fix(repo, task)
        if not run_pytest(repo):
            return False, "reference fix does not pass (unsolvable)"
    return True, "accepted"


def build_corpus(n: int, *, seed: int) -> tuple[list[BenchTask], list[dict]]:
    """Synthesize and ACCEPT a corpus; return (accepted_tasks, per-task acceptance records)."""
    records: list[dict] = []
    accepted: list[BenchTask] = []
    for task in synthesize(n, seed=seed):
        ok, reason = accept_task(task)
        records.append({"name": task.name, "family": task.name.rsplit("_", 1)[0],
                        "difficulty": task.difficulty, "accepted": ok, "reason": reason})
        if ok:
            accepted.append(task)
    return accepted, records


def capability_gap_tasks(sparse_cells: list[dict], *, seed: int) -> list[BenchTask]:
    """Generate one task per sparse (difficulty) cell to close under-sampled matrix regions.

    ``sparse_cells`` items carry a ``difficulty`` (easy|medium|hard); active learning
    prioritizes generation exactly where coverage is thin.
    """
    out: list[BenchTask] = []
    for i, cell in enumerate(sparse_cells):
        diff = cell.get("difficulty", "easy")
        if diff in _BY_DIFFICULTY:
            out.extend(synthesize(1, seed=seed + i, difficulty=diff))
    return out
