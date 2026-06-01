"""Calibrated evaluator loop (round-4 Block H)."""

from __future__ import annotations

import pytest

from acp.evaluation.calibration import (
    CalibrationSample,
    calibrate,
    recommend_human_review_threshold,
)


def test_calibration_report_has_per_signal_and_threshold() -> None:
    samples = [
        CalibrationSample(0.9, True, "objective"),
        CalibrationSample(0.8, True, "objective"),
        CalibrationSample(0.2, False, "objective"),
        CalibrationSample(0.6, True, "weak"),
        CalibrationSample(0.4, False, "weak"),
    ]
    rep = calibrate(samples).to_dict()
    assert set(rep["by_source"]) == {"objective", "weak"}
    for src in ("objective", "weak"):
        assert "brier" in rep["by_source"][src] and "correlation" in rep["by_source"][src]
    tr = rep["threshold_recommendation"]
    assert 0.0 < tr["threshold"] < 1.0
    assert "false_confident_pass" in tr and "auto_approvable_fraction" in tr


def test_bad_weak_signal_gets_low_score() -> None:
    # a weak signal that predicts the OPPOSITE of the truth
    bad = [CalibrationSample(0.9, False, "weak"), CalibrationSample(0.1, True, "weak"),
           CalibrationSample(0.8, False, "weak"), CalibrationSample(0.2, True, "weak")]
    good = [CalibrationSample(0.9, True, "objective"), CalibrationSample(0.1, False, "objective")]
    rep = calibrate(bad + good).to_dict()
    assert rep["by_source"]["weak"]["accuracy"] == 0.0
    assert rep["by_source"]["weak"]["brier"] > rep["by_source"]["objective"]["brier"]
    assert rep["by_source"]["weak"]["correlation"] < 0


def test_post_merge_revert_reduces_calibration_truth() -> None:
    # objective predicted pass; baseline truth says pass too
    base = [CalibrationSample(0.9, True, "objective", "post_merge")]
    acc_before = calibrate(base).accuracy
    # a revert flips the truth to fail while the predictor still said pass -> wrong
    reverted = base + [CalibrationSample(0.9, False, "objective", "post_merge")]
    acc_after = calibrate(reverted).accuracy
    assert acc_after < acc_before


def test_human_label_overrides_objective_success() -> None:
    # objective is highly confident (0.95 -> "pass") but the human says FAIL
    s = [CalibrationSample(0.95, False, "objective", "human")]
    rep = calibrate(s)
    assert rep.accuracy == 0.0  # human truth wins; the confident pass is counted wrong
    assert rep.brier > 0.8


def test_threshold_recommendation_empty_is_safe() -> None:
    tr = recommend_human_review_threshold([])
    assert tr["threshold"] == 0.5


# --- service: persisted calibration EvalRun ---------------------------------
@pytest.fixture
def service(tmp_path):
    from acp.api.service import AppService
    from acp.core.config import ACPSettings
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'cal.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_calibration_report_persisted(service) -> None:
    from acp.schemas.evaluation import EvaluationResult, WeakLabel
    from acp.schemas.human_review import HumanLabel

    # two attempts with objective + weak predictions and human ground truth
    service._save(
        EvaluationResult(task_id="t", attempt_id="a1", spec_compliance=0.9),
        EvaluationResult(task_id="t", attempt_id="a2", spec_compliance=0.85),
        WeakLabel(task_id="t", attempt_id="a1", probabilities={"success": 0.8}),
        WeakLabel(task_id="t", attempt_id="a2", probabilities={"success": 0.3}),
        HumanLabel(review_item_id="r1", task_id="t", attempt_id="a1", verdict="pass"),
        HumanLabel(review_item_id="r2", task_id="t", attempt_id="a2", verdict="fail"),
    )
    report = service.calibrate_evaluators()
    assert "threshold_recommendation" in report
    assert set(report["by_source"]) == {"objective", "weak"}
    # durable as EvalRun(kind=calibration)
    runs = [r for r in service.list_eval_runs() if r["kind"] == "calibration"]
    assert runs, "no calibration EvalRun persisted"
