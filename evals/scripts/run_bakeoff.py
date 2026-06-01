"""Adapter bakeoff (charter §21.5): compare available adapters on fixture tasks."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from acp.api.service import AppService
from acp.cli.demos import make_demo_repo
from acp.core.config import ACPSettings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overnight", action="store_true")
    ap.add_argument("--out", default="evals/reports/bakeoff.json")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'bake.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
    )
    svc = AppService(settings)
    repo_path = make_demo_repo(tmp / "repo")
    repo = svc.create_repo("bakeoff", repo_path, default_branch="master")
    fixed = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"

    # Matrix: task class x context strategy (charter §21.5 / round-1 §8).
    task_classes = [
        ("bugfix", "Fix divide bug", "zero divisor"),
        ("feature", "Add subtract function", "implement subtract"),
        ("docs", "Update README", "improve docs in README.md"),
    ]
    strategies = ["minimal", "hybrid_keyword_embedding", "bug_reproduction"]

    cells = []
    for cls_name, title, body in task_classes:
        for strat in strategies:
            task = svc.create_task(repo.id, title=title, body=body,
                                   metadata={"files": {"calculator.py": fixed},
                                             "context_strategy": strat})
            state = svc.run_task(task.id)
            status = state.status if isinstance(state.status, str) else state.status.value
            runner = svc._runners.get(state.run_id)
            cost = sum(a.estimated_cost_usd for a in runner.artifacts.attempts) if runner else 0.0
            latency = sum(a.wall_time_s for a in runner.artifacts.attempts) if runner else 0.0
            cells.append({
                "task_class": cls_name, "strategy": strat, "status": status,
                "attempts": len(state.attempt_ids),
                "cost_usd": round(cost, 4), "latency_s": round(latency, 3),
                "human_review": status == "waiting_for_human",
            })

    succeeded = sum(1 for c in cells if c["status"] == "succeeded")
    report = {
        "adapters": svc.registry.names(),
        "matrix": cells,
        "summary": {
            "cells": len(cells),
            "success_rate": round(succeeded / len(cells), 3),
            "human_review_rate": round(
                sum(c["human_review"] for c in cells) / len(cells), 3
            ),
            "total_latency_s": round(sum(c["latency_s"] for c in cells), 3),
        },
        "recommendation": "route docs to minimal context, bugfix to bug_reproduction",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
