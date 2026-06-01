"""Agent attempt, tool calls, plans, health (charter §7.3, §12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.enums import AgentKind, RunStatus
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class AgentHealth(ACPModel):
    name: str
    kind: AgentKind
    available: bool
    detail: str = ""


class Budget(ACPModel):
    max_cost_usd: float = 5.0
    max_wall_time_s: int = 600
    token_budget: int = 80_000
    seed: int = 1234


class AgentPlan(ACPModel):
    summary: str = ""
    steps: list[str] = Field(default_factory=list)
    estimated_cost_usd: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(ACPModel):
    id: str = Field(default_factory=lambda: new_id("tool"))
    attempt_id: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    result_artifact_ref: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    error: str | None = None


class AgentAttempt(ACPModel):
    id: str = Field(default_factory=lambda: new_id("attempt"))
    task_id: str
    routing_decision_id: str | None = None
    workspace_id: str | None = None
    agent_kind: AgentKind
    agent_name: str
    model_name: str | None = None
    status: RunStatus = RunStatus.PENDING
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    input_token_count: int = 0
    output_token_count: int = 0
    total_token_count: int = 0
    estimated_cost_usd: float = 0.0
    wall_time_s: float = 0.0
    diff_bundle_id: str | None = None
    trace_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentReviewResult(ACPModel):
    verdict: str = "uncertain"  # pass | fail | partial | uncertain
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    comments: list[str] = Field(default_factory=list)


class AgentAttemptResult(ACPModel):
    """What an adapter returns from ``execute``."""

    status: RunStatus
    diff: DiffBundleRef | None = None
    input_token_count: int = 0
    output_token_count: int = 0
    estimated_cost_usd: float = 0.0
    wall_time_s: float = 0.0
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiffBundleRef(ACPModel):
    """Lightweight diff payload an adapter returns (resolved to DiffBundle)."""

    unified_diff: str = ""
    changed_files: list[str] = Field(default_factory=list)
