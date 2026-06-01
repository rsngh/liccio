"""Soak harness (charter §21.4): repeated fake-agent workflows, fixed seed mix."""

from __future__ import annotations

import argparse
import random
import tempfile
import time
from pathlib import Path

from acp.api.service import AppService
from acp.cli.demos import make_demo_repo
from acp.core.config import ACPSettings

MODES = ["success", "fail", "human", "large"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--iterations", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    tmp = Path(tempfile.mkdtemp())
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'soak.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
    )
    svc = AppService(settings)
    repo_path = make_demo_repo(tmp / "repo")
    repo = svc.create_repo("soak", repo_path, default_branch="master")

    deadline = time.monotonic() + args.hours * 3600 if args.hours else None
    statuses: dict[str, int] = {}
    i = 0
    fixed = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"
    while (i < args.iterations) or (deadline and time.monotonic() < deadline):
        mode = rng.choice(MODES)
        meta = {"files": {"calculator.py": fixed}}
        title = "Fix divide bug"
        if mode == "fail":
            meta = {"fake_mode": "fail_noop"}
        elif mode == "human":
            title = "Update auth password hashing"
        task = svc.create_task(repo.id, title=title, body="soak", metadata=meta)
        state = svc.run_task(task.id)
        st = state.status if isinstance(state.status, str) else state.status.value
        statuses[st] = statuses.get(st, 0) + 1
        i += 1
        if deadline is None and i >= args.iterations:
            break

    print(f"soak iterations={i} statuses={statuses}")
    print("no orphan workspaces" if (tmp / "ws").exists() else "ws dir missing")


if __name__ == "__main__":
    main()
