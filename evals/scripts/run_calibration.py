"""Generate the evaluator-calibration artifact (round-4 Block H / I).

Seeds a small labelled dataset (objective + weak signals vs human truth, with a
post-merge revert) and writes evals/reports/calibration.json — including the
per-signal Brier/accuracy/correlation and the human-review threshold
recommendation.

    uv run python evals/scripts/run_calibration.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.schemas.evaluation import EvaluationResult, WeakLabel
from acp.schemas.human_review import HumanLabel
from acp.schemas.learning import PostMergeOutcome

REPORT = Path("evals/reports/calibration.json")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'cal.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws"))
    svc._save(
        EvaluationResult(task_id="t", attempt_id="a1", spec_compliance=0.92),
        EvaluationResult(task_id="t", attempt_id="a2", spec_compliance=0.80),
        EvaluationResult(task_id="t", attempt_id="a3", spec_compliance=0.30),
        EvaluationResult(task_id="t", attempt_id="a4", spec_compliance=0.88),
        WeakLabel(task_id="t", attempt_id="a1", probabilities={"success": 0.85}),
        WeakLabel(task_id="t", attempt_id="a2", probabilities={"success": 0.40}),
        WeakLabel(task_id="t", attempt_id="a3", probabilities={"success": 0.20}),
        HumanLabel(review_item_id="r1", task_id="t", attempt_id="a1", verdict="pass"),
        HumanLabel(review_item_id="r2", task_id="t", attempt_id="a2", verdict="fail"),
        HumanLabel(review_item_id="r3", task_id="t", attempt_id="a3", verdict="fail"),
        # a4 looked good objectively but was reverted post-merge (truth = fail)
        PostMergeOutcome(task_id="t", attempt_id="a4", reverted=True),
    )
    report = svc.calibrate_evaluators()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))
    tr = report["threshold_recommendation"]
    print(f"calibration: n={report['n']} acc={report['accuracy']} "
          f"brier={report['brier']} human_review_threshold={tr['threshold']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
