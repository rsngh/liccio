"""Calibrate evaluators from persisted human + post-merge labels (round-3 R3-6)."""

from __future__ import annotations

import pytest

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import HumanVerdict
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.human_review import HumanLabel
from acp.schemas.learning import PostMergeOutcome


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'c.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def test_calibration_from_db(service) -> None:
    # well-calibrated objective evaluator: high spec_compliance -> human pass /
    # not reverted; low -> fail / reverted.
    service._save(
        EvaluationResult(task_id="t1", attempt_id="a1", spec_compliance=0.95),
        EvaluationResult(task_id="t2", attempt_id="a2", spec_compliance=0.1),
        HumanLabel(review_item_id="r1", task_id="t1", attempt_id="a1",
                   verdict=HumanVerdict.PASS, score=0.9),
        HumanLabel(review_item_id="r2", task_id="t2", attempt_id="a2",
                   verdict=HumanVerdict.FAIL),
        PostMergeOutcome(task_id="t1", attempt_id="a1", merged=True, reverted=False),
        PostMergeOutcome(task_id="t2", attempt_id="a2", reverted=True),
    )
    report = service.calibrate_evaluators()
    assert report["n"] == 4  # 2 human + 2 post-merge
    assert report["accuracy"] == 1.0
    assert report["brier"] < 0.1
    # persisted as an eval run
    assert any(r["kind"] == "calibration" for r in service.list_eval_runs())
