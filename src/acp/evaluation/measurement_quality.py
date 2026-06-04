"""Measurement-quality scoring (Alpha 13 WS3).

Turns a batch of attempt cells into a per-dimension trust score, then a policy
verdict. The score feeds the capability matrix (per-cell measurement_quality_mean)
and the production health gate, so a contaminated or harness-degraded measurement
cannot silently drive a routing change.
"""

from __future__ import annotations

from typing import Any

from acp.evaluation.measurement_hygiene import classify_record
from acp.schemas.measurement_quality import (
    MeasurementQualityPolicy,
    MeasurementQualityReport,
    MeasurementQualityScore,
)


def score_measurement_quality(
    cells: list[Any], *, secret_clean: bool = True, artifact_complete: bool = True,
    harness_available: bool = True,
) -> MeasurementQualityScore:
    """Score the trustworthiness of a measurement batch (0..1 per dimension).

    ``secret_clean`` / ``artifact_complete`` / ``harness_available`` are external
    facts the caller supplies (leak scan, manifest validity, availability audit).
    """
    records = [classify_record(c) for c in cells]
    n = len(records)
    if not n:
        return MeasurementQualityScore(sample_size=0)
    harness = [r for r in records if (r.tool_calls or 0) >= 0]  # all carry the signal

    def frac(pred) -> float:
        return round(sum(1 for r in records if pred(r)) / n, 4)

    infra_clean = 1.0 - frac(lambda r: r.is_infra and not r.is_success)
    # Every infra/provider attempt should carry an attribution kind (the classifier
    # always assigns one) -> attribution is complete unless an infra row lacks a kind.
    infra_rows = [r for r in records if r.is_infra]
    timeout_attribution = (1.0 if not infra_rows else round(
        sum(1 for r in infra_rows if r.infra_failure_kind) / len(infra_rows), 4))
    # No provider_retry_exceeded means the no-retry provider policy held.
    provider_policy_compliance = 1.0 - frac(
        lambda r: r.provider_failure_kind == "retry_exceeded")
    tool_activation_validity = (round(
        sum(1 for r in harness if r.tool_activation_valid) / len(harness), 4)
        if harness else 1.0)
    verification_validity = frac(lambda r: r.verification_valid)
    dims = {
        "provider_policy_compliance": provider_policy_compliance,
        "timeout_attribution": timeout_attribution,
        "tool_activation_validity": tool_activation_validity,
        "verification_validity": verification_validity,
        "secret_clean": 1.0 if secret_clean else 0.0,
        "artifact_complete": 1.0 if artifact_complete else 0.0,
        "infra_clean": round(infra_clean, 4),
        "harness_available": 1.0 if harness_available else 0.0,
    }
    overall = round(sum(dims.values()) / len(dims), 4)
    return MeasurementQualityScore(**dims, overall=overall, sample_size=n)


def measurement_quality_report(
    cells: list[Any], *, policy: MeasurementQualityPolicy | None = None, **facts: Any,
) -> MeasurementQualityReport:
    """Score a batch and apply a trust policy."""
    pol = policy or MeasurementQualityPolicy()
    score = score_measurement_quality(cells, **facts)
    trusted, reasons = pol.evaluate(score)
    return MeasurementQualityReport(score=score, trusted=trusted, block_reasons=reasons)
