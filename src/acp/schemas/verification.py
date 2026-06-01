"""Verification plan, run, and evidence schemas (charter §7.3, §14)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.enums import EvidenceKind, EvidenceStatus, RiskLevel
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class VerificationPlan(ACPModel):
    id: str = Field(default_factory=lambda: new_id("vplan"))
    task_id: str
    strategy: str = "standard"
    required_commands: list[list[str]] = Field(default_factory=list)
    optional_commands: list[list[str]] = Field(default_factory=list)
    ui_flows: list[str] = Field(default_factory=list)
    static_checks: list[list[str]] = Field(default_factory=list)
    security_checks: list[list[str]] = Field(default_factory=list)
    coverage_checks: list[list[str]] = Field(default_factory=list)
    mutation_checks: list[list[str]] = Field(default_factory=list)
    acceptance_assertions: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    created_at: datetime = Field(default_factory=utcnow)


class Evidence(ACPModel):
    id: str = Field(default_factory=lambda: new_id("evid"))
    task_id: str
    attempt_id: str | None = None
    verification_run_id: str | None = None
    kind: EvidenceKind
    name: str
    status: EvidenceStatus
    score: float | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: str = ""
    raw_output_ref: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationRun(ACPModel):
    id: str = Field(default_factory=lambda: new_id("vrun"))
    task_id: str
    attempt_id: str | None = None
    plan_id: str | None = None
    status: EvidenceStatus = EvidenceStatus.SKIPPED
    evidence_ids: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
