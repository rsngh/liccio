"""Run a vendor harness across the graded benchmark suite (Alpha 23 WS3).

Drives a :class:`VendorNativeHarness` over every task in ``BENCH_TASKS`` (optionally with
an injected skill), collects measurement-trust cells, and aggregates a solve rate OVERALL
and PER DIFFICULTY using the hygiene layer (conclusive attempts only; timeouts are infra,
never capability failures). The result is the honest capability-by-difficulty profile the
canary / transfer / capability-matrix machinery consumes.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS, DIFFICULTIES, BenchTask, build_bench_repo
from acp.agents.vendor_native import VendorNativeHarness
from acp.evaluation.measurement_hygiene import build_hygiene_report


@dataclass
class TaskResult:
    name: str
    difficulty: str
    solved: bool
    conclusive: bool
    outcome: str
    wall_time_s: float
    secret_leak: bool
    activated: bool = True       # harness actually edited/solved (vs a no-op return)


@dataclass
class BenchmarkResult:
    harness: str
    skill_injected: bool
    overall_solve_rate: float
    n_conclusive: int
    n_attempts: int
    contaminated: bool
    by_difficulty: dict = field(default_factory=dict)  # diff -> {solve_rate, n_*}
    tasks: list = field(default_factory=list)          # TaskResult dicts
    activation_rate: float = 1.0                       # share of attempts that activated
    activated_solve_rate: float = 0.0                  # solve rate over activated attempts

    def to_dict(self) -> dict:
        return {
            "harness": self.harness, "skill_injected": self.skill_injected,
            "overall_solve_rate": self.overall_solve_rate,
            "activation_rate": self.activation_rate,
            "activated_solve_rate": self.activated_solve_rate,
            "n_conclusive": self.n_conclusive, "n_attempts": self.n_attempts,
            "contaminated": self.contaminated, "by_difficulty": self.by_difficulty,
            "tasks": self.tasks,
        }


def _agg(cells: list[dict]) -> dict:
    rep = build_hygiene_report(cells)
    return {"solve_rate": rep.solve_rate, "n_conclusive": rep.n_conclusive,
            "n_attempts": rep.n_attempts, "contaminated": rep.contaminated}


def run_benchmark(harness: VendorNativeHarness, *, tasks: list[BenchTask] | None = None,
                  skill_content: str | None = None, timeout_s: int = 180,
                  reps: int = 1) -> BenchmarkResult:
    """Run ``harness`` over the suite; aggregate solve rate overall + per difficulty.

    ``reps`` repeats every task (averaged via the cell pool) to smooth single-run noise.
    Each task runs in its own throwaway repo so attempts never contaminate each other.
    """
    tasks = tasks or BENCH_TASKS
    all_cells: list[dict] = []
    cells_by_diff: dict[str, list[dict]] = {d: [] for d in DIFFICULTIES}
    task_results: list[dict] = []
    for task in tasks:
        for _ in range(max(1, reps)):
            with tempfile.TemporaryDirectory() as d:
                repo = build_bench_repo(Path(d), task)
                res = harness.run_task(repo, task.prompt, task_type=task.difficulty,
                                       task_name=task.name, timeout_s=timeout_s,
                                       skill_content=skill_content)
            cell = res.to_cell()
            all_cells.append(cell)
            cells_by_diff[task.difficulty].append(cell)
            task_results.append(TaskResult(
                name=task.name, difficulty=task.difficulty, solved=res.no_patch_solve,
                conclusive=res.outcome in ("task_success", "task_failure"),
                outcome=res.outcome, wall_time_s=res.wall_time_s,
                secret_leak=res.secret_leak,
                activated=bool(res.diff_captured or res.no_patch_solve)).__dict__)
    overall = _agg(all_cells)
    by_diff = {d: _agg(cells_by_diff[d]) for d in DIFFICULTIES if cells_by_diff[d]}
    # Activation-aware view (Alpha 26): a vendor no-op (no diff, no solve) is an activation
    # failure, not a capability failure. Report the share that activated and the solve rate
    # over only those — so a degraded CLI can never look like a low-capability result.
    activated = [t for t in task_results if t["activated"]]
    activation_rate = round(len(activated) / len(task_results), 4) if task_results else 1.0
    activated_solve = (round(sum(t["solved"] for t in activated) / len(activated), 4)
                       if activated else 0.0)
    return BenchmarkResult(
        harness=harness.spec.name, skill_injected=bool(skill_content),
        overall_solve_rate=overall["solve_rate"], n_conclusive=overall["n_conclusive"],
        n_attempts=overall["n_attempts"], contaminated=overall["contaminated"],
        by_difficulty=by_diff, tasks=task_results, activation_rate=activation_rate,
        activated_solve_rate=activated_solve)
