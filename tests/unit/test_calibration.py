"""Evaluator calibration (round-3 R3-6)."""

from __future__ import annotations

from acp.evaluation.calibration import CalibrationSample, calibrate


def test_perfect_predictor() -> None:
    samples = [
        CalibrationSample(predicted=0.95, truth=True),
        CalibrationSample(predicted=0.9, truth=True),
        CalibrationSample(predicted=0.05, truth=False),
        CalibrationSample(predicted=0.1, truth=False),
    ]
    rep = calibrate(samples)
    assert rep.accuracy == 1.0
    assert rep.brier < 0.05
    assert rep.correlation > 0.9


def test_anticorrelated_predictor_low_accuracy() -> None:
    samples = [
        CalibrationSample(predicted=0.95, truth=False),
        CalibrationSample(predicted=0.9, truth=False),
        CalibrationSample(predicted=0.05, truth=True),
    ]
    rep = calibrate(samples)
    assert rep.accuracy == 0.0
    assert rep.correlation < 0.0


def test_by_source_breakdown() -> None:
    samples = [
        CalibrationSample(predicted=0.9, truth=True, source="objective"),
        CalibrationSample(predicted=0.2, truth=False, source="weak"),
    ]
    rep = calibrate(samples)
    d = rep.to_dict()
    assert set(d["by_source"]) == {"objective", "weak"}
    assert d["n"] == 2


def test_empty_is_safe() -> None:
    assert calibrate([]).n == 0
