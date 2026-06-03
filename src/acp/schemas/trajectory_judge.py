"""Schemas for the relative trajectory judge (Alpha 11/12 §WS9).

Where :mod:`acp.learning.preference` consumes *absolute* per-attempt labels, the
relative trajectory judge compares two trajectories head-to-head on several axes
and emits a *relative* preference plus per-axis rewards. These models capture the
judge's output so preference learning, cross-judge audits and reward-sensitivity
reports can consume it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from acp.schemas.base import ACPModel

Winner = Literal["a", "b", "tie"]


class PerAxisReward(ACPModel):
    """One axis of comparison: scores for each trajectory and the axis winner."""

    axis: str
    score_a: float
    score_b: float
    winner: Winner
    detail: str = ""


class TrajectoryComparison(ACPModel):
    """Relative comparison of two trajectories across all axes."""

    overall_winner: Winner
    per_axis: list[PerAxisReward] = Field(default_factory=list)
    margin: float = 0.0


class CrossJudgeAudit(ACPModel):
    """Agreement between the independent axis judges and the overall verdict."""

    axes_agreement: float = 0.0
    dissenting_axes: list[str] = Field(default_factory=list)


class RewardSensitivityReport(ACPModel):
    """Leave-one-out influence of each axis on the overall preference."""

    influence: dict[str, float] = Field(default_factory=dict)
