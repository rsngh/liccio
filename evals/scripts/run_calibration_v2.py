"""Evaluator calibration v2 artifact (round-5 WS9/WS15).

    uv run python evals/scripts/run_calibration_v2.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acp.api.service import AppService
from acp.core.config import ACPSettings

REPORT = Path("evals/reports/calibration_v2.json")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'c2.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws"))
    run = svc.calibrate_evaluators_v2()
    report = svc.get_eval_report(run.id)["content"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))
    print(f"calibration v2: recommended_threshold={report['recommended_threshold']} "
          f"evaluators={len(report['evaluators'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
