"""Soak harness with operational metrics (round-1 two-day D2B5).

Runs repeated workflows and tracks memory, file descriptors, workspace dirs,
git worktrees, artifact bytes, DB rows, status distribution, latency percentiles,
and policy arm stats — emitting a machine-readable report with threshold checks.
"""

from __future__ import annotations

import os
import resource
import statistics
import time
from pathlib import Path

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"

TASK_MIX: dict[str, tuple[str, str, dict]] = {
    "bugfix": ("Fix divide bug", "zero divisor", {"files": {"calculator.py": FIXED}}),
    "fail": ("Broken attempt", "fail", {"fake_mode": "fail_noop"}),
    "human": ("Update auth password hashing", "auth", {"files": {"calculator.py": FIXED}}),
}


def _rss_kb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _open_fds() -> int:
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return -1


def _count_worktrees(workspace_dir: Path) -> int:
    if not workspace_dir.exists():
        return 0
    return sum(1 for p in workspace_dir.iterdir() if p.is_dir())


def _artifact_bytes(artifact_dir: Path) -> int:
    if not artifact_dir.exists():
        return 0
    return sum(f.stat().st_size for f in artifact_dir.rglob("*") if f.is_file())


def run_soak(
    service, repo_id: str, iterations: int = 20, seed: int = 1234,
    task_mix: list[str] | None = None,
) -> dict:
    import random

    rng = random.Random(seed)
    mix = task_mix or list(TASK_MIX.keys())
    settings = service.settings
    ws_dir = Path(settings.workspace_dir)
    art_dir = Path(settings.artifact_dir)

    rss_start = _rss_kb()
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    run_ids: list[str] = []
    workspace_paths: set[str] = set()

    for _ in range(iterations):
        kind = rng.choice(mix)
        title, body, meta = TASK_MIX[kind]
        task = service.create_task(repo_id, title=title, body=body, metadata=dict(meta))
        t0 = time.monotonic()
        state = service.run_task(task.id)
        latencies.append(time.monotonic() - t0)
        st = state.status if isinstance(state.status, str) else state.status.value
        statuses[st] = statuses.get(st, 0) + 1
        run_ids.append(state.run_id)
        workspace_paths.update(state.scratch.get("workspaces", {}).values())

    rss_end = _rss_kb()
    arms = {ctx: len(a) for ctx, a in getattr(service.policy, "arms", {}).items()}
    lat_sorted = sorted(latencies)

    def pct(p: float) -> float:
        if not lat_sorted:
            return 0.0
        idx = min(len(lat_sorted) - 1, int(p * len(lat_sorted)))
        return round(lat_sorted[idx], 3)

    mem_growth = (rss_end - rss_start) / rss_start if rss_start else 0.0
    report = {
        "iterations": iterations,
        "status_distribution": statuses,
        "unique_run_ids": len(set(run_ids)),
        "unique_workspaces": len(workspace_paths),
        "rss_kb_start": rss_start,
        "rss_kb_end": rss_end,
        "memory_growth_ratio": round(mem_growth, 4),
        "open_fds": _open_fds(),
        "worktree_dirs": _count_worktrees(ws_dir),
        "artifact_bytes": _artifact_bytes(art_dir),
        "latency_p50": pct(0.5),
        "latency_p95": pct(0.95),
        "latency_mean": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "policy_arm_contexts": arms,
        "thresholds": {
            "memory_growth_ok": mem_growth < 0.25,
            "no_unbounded_worktrees": _count_worktrees(ws_dir) <= iterations + 2,
            "all_runs_unique": len(set(run_ids)) == len(run_ids),
        },
    }
    return report


def soak_to_markdown(report: dict) -> str:
    lines = ["# Soak report", ""]
    for k, v in report.items():
        if k != "status_distribution":
            lines.append(f"- {k}: {v}")
    lines.append(f"- status_distribution: {report['status_distribution']}")
    return "\n".join(lines)
