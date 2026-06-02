"""Tests for Alpha-9 drift detection + auto-demote (src/acp/learning/drift.py)."""

from __future__ import annotations

from acp.learning.drift import (
    AutoDemoter,
    DriftReport,
    WindowedOutcome,
    detect_drift,
)


def _w(pred: float, realized: bool, risk: str = "low", ordinal: int = 0) -> WindowedOutcome:
    return WindowedOutcome(prediction=pred, realized=realized, risk_level=risk, ordinal=ordinal)


def _stable_window(ordinal_start: int = 0) -> list[WindowedOutcome]:
    # 8 correct, 2 wrong -> 0.8 accuracy; probs clustered around 0.2 / 0.8.
    rows = [
        _w(0.85, True), _w(0.82, True), _w(0.78, True), _w(0.9, True),
        _w(0.2, False), _w(0.15, False), _w(0.25, False), _w(0.18, False),
        _w(0.6, False), _w(0.45, True),  # the two "wrong" ones
    ]
    for i, r in enumerate(rows):
        r.ordinal = ordinal_start + i
    return rows


def test_no_drift_stable_accuracy_low_psi() -> None:
    baseline = _stable_window(0)
    recent = _stable_window(100)  # identical distribution / accuracy
    report = detect_drift(baseline, recent)
    assert isinstance(report, DriftReport)
    assert report.accuracy_drop <= 0.0
    assert report.psi <= 0.25
    assert report.drifted is False
    assert report.demote_recommended is False
    assert report.reasons == []


def test_accuracy_decay_triggers_drift_and_demote() -> None:
    baseline = _stable_window(0)
    # Recent window: model now mostly wrong (predicts viable, truth false).
    recent = [_w(0.85, False, ordinal=200 + i) for i in range(8)]
    recent += [_w(0.8, True, ordinal=210), _w(0.82, True, ordinal=211)]
    report = detect_drift(baseline, recent)
    assert report.accuracy_drop > 0.1
    assert report.drifted is True
    assert report.demote_recommended is True
    assert any("accuracy_drop" in r for r in report.reasons)


def test_psi_shift_triggers_drift() -> None:
    # Baseline probs clustered low; recent clustered high -> large PSI. Keep
    # accuracy steady so PSI is the sole trigger.
    baseline = [_w(0.05, False, ordinal=i) for i in range(10)]
    recent = [_w(0.95, True, ordinal=100 + i) for i in range(10)]
    report = detect_drift(baseline, recent)
    assert report.psi > 0.25
    assert report.drifted is True
    assert any("psi" in r for r in report.reasons)


def test_recent_high_risk_false_negative_recommends_demote() -> None:
    # Accuracy fine, PSI fine, but one recent HIGH-risk false negative present:
    # predicted viable (>=0.5) while truth was not viable.
    baseline = _stable_window(0)
    recent = _stable_window(100)
    recent[0] = _w(0.9, False, risk="high", ordinal=100)
    report = detect_drift(baseline, recent)
    assert report.high_risk_false_negative_rate_recent > 0
    assert report.demote_recommended is True
    assert any("high-risk false-negative" in r for r in report.reasons)


class _FakeEnsemble:
    def __init__(self, promoted: bool) -> None:
        self.learned_promoted = promoted


def test_autodemoter_flips_promoted_to_advisory() -> None:
    ensemble = _FakeEnsemble(promoted=True)
    report = DriftReport(
        baseline_accuracy=0.9, recent_accuracy=0.5, accuracy_drop=0.4,
        psi=0.4, high_risk_false_negative_rate_recent=0.0,
        drifted=True, demote_recommended=True, reasons=["x"])
    demoted = AutoDemoter().apply(ensemble, report)
    assert demoted is True
    assert ensemble.learned_promoted is False


def test_autodemoter_noop_when_already_advisory() -> None:
    ensemble = _FakeEnsemble(promoted=False)
    report = DriftReport(
        baseline_accuracy=0.9, recent_accuracy=0.5, accuracy_drop=0.4,
        psi=0.4, high_risk_false_negative_rate_recent=0.0,
        drifted=True, demote_recommended=True, reasons=["x"])
    demoted = AutoDemoter().apply(ensemble, report)
    assert demoted is False
    assert ensemble.learned_promoted is False


def test_autodemoter_noop_when_no_demote_recommended() -> None:
    ensemble = _FakeEnsemble(promoted=True)
    report = DriftReport(
        baseline_accuracy=0.9, recent_accuracy=0.9, accuracy_drop=0.0,
        psi=0.0, high_risk_false_negative_rate_recent=0.0,
        drifted=False, demote_recommended=False, reasons=[])
    demoted = AutoDemoter().apply(ensemble, report)
    assert demoted is False
    assert ensemble.learned_promoted is True
