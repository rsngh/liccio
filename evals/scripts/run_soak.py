"""Soak runner with operational metrics (round-1 two-day D2B5)."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from acp.api.service import AppService
from acp.cli.demos import make_demo_repo
from acp.core.config import ACPSettings
from acp.evaluation.soak import run_concurrent_soak, run_soak, soak_to_markdown


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=50)
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--concurrency", type=int, default=1)  # reserved
    ap.add_argument("--task-mix", default="bugfix,fail,human")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out-json", default="evals/reports/soak.json")
    ap.add_argument("--out-md", default="evals/reports/soak.md")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'soak.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
    )
    svc = AppService(settings)
    repo = svc.create_repo("soak", make_demo_repo(tmp / "repo"), default_branch="master")
    mix = args.task_mix.split(",")

    if args.concurrency > 1:
        report = run_concurrent_soak(settings, repo.id, iterations=args.iterations,
                                     concurrency=args.concurrency, seed=args.seed, task_mix=mix)
    elif args.hours:
        deadline = time.monotonic() + args.hours * 3600
        total = 0
        report: dict = {}
        while time.monotonic() < deadline:
            report = run_soak(svc, repo.id, iterations=args.iterations, seed=args.seed,
                              task_mix=mix)
            total += args.iterations
        report["iterations"] = total
    else:
        report = run_soak(svc, repo.id, iterations=args.iterations, seed=args.seed,
                          task_mix=mix)

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    Path(args.out_md).write_text(soak_to_markdown(report))
    print(f"iterations={report['iterations']} statuses={report['status_distribution']} "
          f"mem_growth={report['memory_growth_ratio']} thresholds={report['thresholds']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
