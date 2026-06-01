"""Task schema (charter §7.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.enums import RiskLevel, RunStatus, TaskType
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class Task(ACPModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    repo_id: str
    source: str = "manual"  # manual | github | ci | ...
    external_id: str | None = None
    title: str
    body: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    task_type: TaskType = TaskType.UNKNOWN
    risk_level: RiskLevel = RiskLevel.MEDIUM
    ambiguity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    labels: list[str] = Field(default_factory=list)
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskClassification(ACPModel):
    """Output of the deterministic task classifier (charter §11)."""

    task_type: TaskType
    risk_level: RiskLevel
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    testability_score: float = Field(ge=0.0, le=1.0)
    affected_modules_estimate: int = 0
    required_verification_kinds: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    reasons: list[str] = Field(default_factory=list)
