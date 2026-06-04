"""The learning gate (Alpha 13 WS2).

A single chokepoint that every learning input (capability matrix, OPE log,
counterfactual log, preference dataset, scheduler training data, health metrics)
must pass an attempt through before it can update a *quality* metric. The rule is
simple and enforced in one place: only a **conclusive** attempt updates solve-rate;
infra / inconclusive attempts update reliability only. This makes "AttemptOutcome is
the boundary between evidence and learning" a mechanical guarantee, not a convention.
"""

from __future__ import annotations

from typing import Any

from acp.evaluation.measurement_hygiene import classify_attempt


def eligible_for_quality(cell: Any) -> bool:
    """True iff this attempt may update a quality metric (solve-rate). Conclusive
    task outcomes only — infra hangs, provider errors, inconclusive are excluded.
    Honors a pre-decided ``_outcome`` (persisted rows) via classify_attempt."""
    return classify_attempt(cell).is_conclusive_quality


def eligible_for_reliability(cell: Any) -> bool:
    """Every attempt counts toward reliability/availability metrics."""
    return True


def gate_quality_samples(cells: list[Any]) -> list[Any]:
    """Filter a list of attempt cells to those eligible for quality learning.

    Use this at the boundary of EVERY quality-updating learner so a contaminated
    or inconclusive attempt can never enter a solve-rate denominator.
    """
    return [c for c in cells if eligible_for_quality(c)]


def split_for_learning(cells: list[Any]) -> tuple[list[Any], list[Any]]:
    """Return (quality_eligible, reliability_only) partition of attempt cells."""
    quality = [c for c in cells if eligible_for_quality(c)]
    reliability_only = [c for c in cells if not eligible_for_quality(c)]
    return quality, reliability_only


class ContaminatedSampleError(ValueError):
    """Raised when a contaminated/inconclusive attempt reaches a quality learner."""


def assert_quality_eligible(cell: Any) -> None:
    """HARD invariant (Alpha 14 WS2): reject any attempt that must not update a
    quality metric. Use at the entry of a strict quality learner to fail loudly
    rather than silently mis-learn from infra noise."""
    if not eligible_for_quality(cell):
        outcome = classify_attempt(cell)
        raise ContaminatedSampleError(
            f"attempt with outcome {getattr(outcome, 'value', outcome)} is not "
            "conclusive-quality and must not update solve-rate / OPE quality reward")
