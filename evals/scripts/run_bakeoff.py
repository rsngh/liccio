"""Bakeoff matrix runner (round-1 two-day D2B4)."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from acp.api.service import AppService
from acp.cli.demos import make_demo_repo
from acp.core.config import ACPSettings
from acp.evaluation.bakeoff import BakeoffConfig, bakeoff_to_markdown, run_bakeoff


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overnight", action="store_true")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out-json", default="evals/reports/bakeoff.json")
    ap.add_argument("--out-md", default="evals/reports/bakeoff.md")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'bake.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
    )
    svc = AppService(settings)
    repo = svc.create_repo("bakeoff", make_demo_repo(tmp / "repo"), default_branch="master")
    cfg = BakeoffConfig(seeds=list(range(1, args.seeds + 1)))
    report = run_bakeoff(svc, repo.id, cfg)

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    Path(args.out_md).write_text(bakeoff_to_markdown(report))
    print(f"cells={report['summary']['cells']} "
          f"success_rate={report['summary']['success_rate']} "
          f"taxonomy={report['failure_taxonomy']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
