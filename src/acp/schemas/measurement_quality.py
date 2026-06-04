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


class DimensionVerdict(ACPModel):
    """One measurement-quality dimension scored against its floor (WS3 v2)."""

    dimension: str
    value: float
    floor: float
    passed: bool


class MeasurementQualityViolation(ACPModel):
    """A dimension that fell below its floor — an independently-actionable defect."""

    dimension: str
    value: float
    floor: float
    detail: str = ""


# The eight quality dimensions, in a stable display order.
QUALITY_DIMENSIONS: tuple[str, ...] = (
    "provider_policy_compliance", "timeout_attribution", "tool_activation_validity",
    "verification_validity", "secret_clean", "artifact_complete", "infra_clean",
    "harness_available",
)


class MeasurementQualityPolicy(ACPModel):
    """Threshold policy with a per-dimension floor map (WS3 v2). A measurement is
    trusted only when ``overall >= min_overall`` AND every dimension meets its floor.
    ``dimension_floors`` defaults are set per dimension below."""

    min_overall: float = 0.8
    require_secret_clean: bool = True
    dimension_floors: dict[str, float] = Field(default_factory=lambda: {
        "provider_policy_compliance": 1.0,  # no hidden-retry budget violations
        "timeout_attribution": 0.9,
        "tool_activation_validity": 0.8,
        "verification_validity": 0.5,
        "secret_clean": 1.0,
        "artifact_complete": 1.0,
        "infra_clean": 0.7,
        "harness_available": 1.0,           # a silently-absent harness disqualifies
    })

    def _floor(self, dimension: str) -> float:
        return self.dimension_floors.get(dimension, 0.0)

    def breakdown(self, score: MeasurementQualityScore) -> list[DimensionVerdict]:
        """Per-dimension verdicts — each independently visible/testable."""
        out: list[DimensionVerdict] = []
        for d in QUALITY_DIMENSIONS:
            value = float(getattr(score, d))
            floor = self._floor(d)
            out.append(DimensionVerdict(dimension=d, value=value, floor=floor,
                                        passed=value >= floor - 1e-9))
        return out

    def violations(self, score: MeasurementQualityScore) -> list[MeasurementQualityViolation]:
        return [MeasurementQualityViolation(dimension=v.dimension, value=v.value,
                                            floor=v.floor,
                                            detail=f"{v.dimension} {v.value:.2f} < {v.floor:.2f}")
                for v in self.breakdown(score) if not v.passed]

    def evaluate(self, score: MeasurementQualityScore) -> tuple[bool, list[str]]:
        """Return (trusted, reasons_if_not) — overall floor + every dimension floor."""
        reasons: list[str] = []
        if score.overall < self.min_overall:
            reasons.append(f"overall {score.overall:.2f} < {self.min_overall}")
        for v in self.violations(score):
            reasons.append(v.detail)
        return (not reasons), reasons


class MeasurementQualityReport(ACPModel):
    """A score plus the policy verdict + per-dimension breakdown over a batch."""

    score: MeasurementQualityScore
    trusted: bool = True
    block_reasons: list[str] = Field(default_factory=list)
    breakdown: list[DimensionVerdict] = Field(default_factory=list)
    violations: list[MeasurementQualityViolation] = Field(default_factory=list)
