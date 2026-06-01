"""Delayed post-merge outcome simulation artifact (round-5 WS8/WS15).

Runs a keyless v2 bakeoff, simulates delayed outcomes, applies them to the
policy, and writes evals/reports/postmerge_sim.json.

    uv run python evals/scripts/run_postmerge_sim.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acp.api.service import AppService
from acp.core.config import ACPSettings

REPORT = Path("evals/reports/postmerge_sim.json")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'pm.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws"))
    run = svc.run_bakeoff_v2(["patch", "fake"], "evals/datasets/no_patch_tasks.yaml")
    result = svc.simulate_postmerge(run.id, seed=1234)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2))
    print(f"postmerge sim: applied={result['applied']} negative={result['negative']} "
          f"negative_rate={result['negative_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
