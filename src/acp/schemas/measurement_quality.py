"""Measurement-quality scoring schemas (Alpha 13 WS3).

A measurement-hygiene report says *what* the outcome distribution was; a
measurement-quality score says *how much to trust it*. Each dimension is 0..1
(higher = cleaner); ``overall`` is their mean. A policy turns the score into a
pass/block decision so a low-quality measurement cannot promote a routing change.
"""

from __future__ import annotations

from pydantic import Field

from acp.schemas.base import ACPModel


class MeasurementQualityScore(ACPModel):
    """Per-dimension trust score for a batch of attempts (0..1, higher cleaner)."""

    provider_policy_compliance: float = Field(default=1.0, ge=0.0, le=1.0)
    timeout_attribution: float = Field(default=1.0, ge=0.0, le=1.0)
    tool_activation_validity: float = Field(default=1.0, ge=0.0, le=1.0)
    verification_validity: float = Field(default=1.0, ge=0.0, le=1.0)
    secret_clean: float = Field(default=1.0, ge=0.0, le=1.0)
    artifact_complete: float = Field(default=1.0, ge=0.0, le=1.0)
    infra_clean: float = Field(default=1.0, ge=0.0, le=1.0)
    harness_available: float = Field(default=1.0, ge=0.0, le=1.0)
    overall: float = Field(default=1.0, ge=0.0, le=1.0)
    sample_size: int = 0


class MeasurementQualityPolicy(ACPModel):
    """Threshold policy: a measurement below ``min_overall`` (or violating any hard
    dimension floor) must not be trusted to update routing."""

    min_overall: float = 0.8
    min_infra_clean: float = 0.7
    min_harness_available: float = 1.0  # a silently-absent harness is disqualifying
    require_secret_clean: bool = True

    def evaluate(self, score: MeasurementQualityScore) -> tuple[bool, list[str]]:
        """Return (trusted, reasons_if_not)."""
        reasons: list[str] = []
        if score.overall < self.min_overall:
            reasons.append(f"overall {score.overall:.2f} < {self.min_overall}")
        if score.infra_clean < self.min_infra_clean:
            reasons.append(f"infra_clean {score.infra_clean:.2f} < {self.min_infra_clean}")
        if score.harness_available < self.min_harness_available:
            reasons.append("a harness was silently absent")
        if self.require_secret_clean and score.secret_clean < 1.0:
            reasons.append("secret leak detected")
        return (not reasons), reasons


class MeasurementQualityReport(ACPModel):
    """A score plus the policy verdict over a measurement batch."""

    score: MeasurementQualityScore
    trusted: bool = True
    block_reasons: list[str] = Field(default_factory=list)
