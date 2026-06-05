"""Timeout-confound detector (Alpha 23 WS8)."""

from __future__ import annotations

import pytest

from acp.evaluation.infra_confound import detect_timeout_confound


def test_gap_that_closes_is_infra_confounded() -> None:
    # The live finding: 0.667 @180s -> 1.0 @240s. The gap closes -> infra, not capability.
    v = detect_timeout_confound(180, 0.667, 240, 1.0)
    assert v.confounded is True
    assert v.gap == pytest.approx(0.333, abs=1e-3)
    assert "infra-confounded" in v.recommendation


def test_budget_insensitive_gap_is_capability() -> None:
    v = detect_timeout_confound(180, 0.8, 240, 0.82)
    assert v.confounded is False
    assert "stable" in v.recommendation


def test_partial_gap_does_not_reach_ceiling() -> None:
    # Relaxing helps a lot but never nears ceiling -> a real capability component remains.
    v = detect_timeout_confound(180, 0.2, 240, 0.45)
    assert v.confounded is False
    assert "partial" in v.recommendation


def test_high_must_exceed_low() -> None:
    with pytest.raises(ValueError):
        detect_timeout_confound(240, 0.5, 180, 0.9)
