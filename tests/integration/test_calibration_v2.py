"""Evaluator calibration v2 — per-evaluator metrics (round-5 WS9)."""

from __future__ import annotations

import pytest

from acp.evaluation.calibration_v2 import (
    EvalCaseV2,
    calibrate_v2,
    default_calibration_dataset,
)

_METRICS = {"accuracy", "precision", "recall", "brier", "ece", "correlation",
            "recommended_threshold", "false_auto_approve_risk"}


def test_per_evaluator_metrics_present() -> None:
    rep = calibrate_v2(default_calibration_dataset()).to_dict()
    assert rep["schema_version"] == 2
    evs = rep["evaluators"]
    assert {"objective", "weak_supervision", "llm_judge", "adversarial_detector",
            "combined", "naive_optimist"}.issubset(set(evs))
    for metrics in evs.values():
        assert _METRICS.issubset(set(metrics))


def test_naive_optimist_has_high_false_auto_approve_risk() -> None:
    evs = calibrate_v2(default_calibration_dataset()).to_dict()["evaluators"]
    # always-pass signal auto-approves bad changes; combined is safer
    assert evs["naive_optimist"]["false_auto_approve_risk"] > \
        evs["combined"]["false_auto_approve_risk"]


def test_adversarial_detector_beats_objective_on_brier() -> None:
    evs = calibrate_v2(default_calibration_dataset()).to_dict()["evaluators"]
    # objective is fooled by hardcoded/test-deletion fixes -> worse Brier
    assert evs["adversarial_detector"]["brier"] < evs["objective"]["brier"]


def test_recommended_threshold_in_range() -> None:
    rep = calibrate_v2(default_calibration_dataset()).to_dict()
    assert 0.0 < rep["recommended_threshold"] < 1.0


def test_empty_is_safe() -> None:
    assert calibrate_v2([]).to_dict()["n_cases"] == 0


@pytest.fixture
def service(tmp_path):
    from acp.api.service import AppService
    from acp.core.config import ACPSettings
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'c2.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_calibration_v2_persists_as_calibration_kind(service) -> None:
    run = service.calibrate_evaluators_v2()
    assert run.kind == "calibration"
    report = service.get_eval_report(run.id)["content"]
    assert report["schema_version"] == 2
    assert "recommended_threshold" in report
    assert report["evaluators"]["objective"]["false_auto_approve_risk"] >= 0.0


def test_custom_cases_smoke() -> None:
    cases = [EvalCaseV2("a", True, {"x": 0.9}), EvalCaseV2("b", False, {"x": 0.1})]
    rep = calibrate_v2(cases).to_dict()
    assert rep["evaluators"]["x"]["accuracy"] == 1.0
