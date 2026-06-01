"""Router-replay artifact (round-5 WS7/WS15).

Runs a keyless v2 bakeoff (patch+fake baselines), replays it into the routing
policy, and writes evals/reports/router_replay.json with the per-context
preference changes — evidence that bakeoff outcomes reshape routing.

    uv run python evals/scripts/run_router_replay.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acp.api.service import AppService
from acp.core.config import ACPSettings

REPORT = Path("evals/reports/router_replay.json")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'rr.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws"))
    run = svc.run_bakeoff_v2(["patch", "fake"], "evals/datasets/no_patch_tasks.yaml")
    result = svc.replay_bakeoff_into_policy(run.id)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2))
    print(f"router replay: applied={result['applied']} "
          f"observations={result['observations']} "
          f"preference_changes={len(result['preference_changes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
