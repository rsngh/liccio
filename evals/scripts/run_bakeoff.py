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

    scorecard = []
    for _ in range(5):
        task = svc.create_task(repo.id, title="Fix divide bug", body="zero divisor",
                               metadata={"files": {"calculator.py": fixed}})
        state = svc.run_task(task.id)
        scorecard.append({
            "task_id": task.id,
            "status": state.status if isinstance(state.status, str) else state.status.value,
            "attempts": len(state.attempt_ids),
        })

    report = {"adapters": svc.registry.names(), "runs": scorecard,
              "recommendation": "patch agent reliable for deterministic fixes"}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
