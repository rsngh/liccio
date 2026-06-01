"""Evaluation result, weak labels (charter §7.3, §15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.enums import WeakLabelValue
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class EvaluationResult(ACPModel):
    id: str = Field(default_factory=lambda: new_id("eval"))
    task_id: str
    attempt_id: str | None = None
    spec_compliance: float = Field(default=0.0, ge=0.0, le=1.0)
    test_adequacy: float = Field(default=0.0, ge=0.0, le=1.0)
    regression_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    security_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    review_burden: float = Field(default=0.0, ge=0.0, le=1.0)
    maintainability: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_human_review: bool = False
    reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class WeakSignal(ACPModel):
    """Output of a single weak-supervision labeling function (charter §15.2)."""

    name: str
    label: WeakLabelValue
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class WeakLabel(ACPModel):
    id: str = Field(default_factory=lambda: new_id("weak"))
    task_id: str
    attempt_id: str | None = None
    label: WeakLabelValue = WeakLabelValue.UNKNOWN
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    signals: list[WeakSignal] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class LLMJudgeResult(ACPModel):
    """Structured output contract for LLM judges (charter §15.3)."""

    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    verdict: str  # pass | fail | partial | uncertain
    reasons: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


class ActiveLearningScore(ACPModel):
    task_id: str
    attempt_id: str | None = None
    priority: float = 0.0
    uncertainty: float = 0.0
    evaluator_disagreement: float = 0.0
    business_risk: float = 0.0
    novelty: float = 0.0
    cost_surprise: float = 0.0
    policy_value_of_information: float = 0.0
    selected: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
