"""Persisted staged-canary run (Alpha 22 WS13).

A staged canary (5% -> 25% -> 50% -> 100%) can outlive a single process: each stage is a
separate live measurement window. Persisting the run + its stage records lets a canary
resume / be audited after a restart, and records exactly what each stage observed and
decided (conclusive N, successes, cost, measurement quality, HAR/HFR/PWL, security
findings, advance/rollback).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class SkillCanaryStageRecord(ACPModel):
    stage: float                       # 0.05 / 0.25 / 0.50 / 1.0
    control_n: int = 0
    canary_n: int = 0
    canary_successes: int = 0
    cost: float = 0.0
    measurement_quality: float = 1.0
    har: float = 0.0
    hfr: float = 0.0
    pwl: float = 0.0
    security_findings: int = 0
    decision: str = "advance"          # advance | rollback
    breaches: list[str] = Field(default_factory=list)


class SkillCanaryRun(ACPModel):
    """A durable staged-canary run for one candidate skill."""

    id: str = Field(default_factory=lambda: new_id("skcan"))
    created_at: datetime = Field(default_factory=utcnow)
    scope_key: str
    candidate_skill_id: str
    baseline_skill_id: str | None = None
    status: str = "running"            # running | promoted | rolled_back
    current_stage: float = 0.0
    stages: list[SkillCanaryStageRecord] = Field(default_factory=list)
    rollback_reason: str = ""
