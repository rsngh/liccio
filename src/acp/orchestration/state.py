"""Workflow state (charter §17.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.enums import RunStatus
from acp.core.ids import new_id, new_trace_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class WorkflowState(ACPModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    task_id: str
    repo_id: str | None = None
    snapshot_id: str | None = None
    context_pack_id: str | None = None
    verification_plan_id: str | None = None
    routing_decision_id: str | None = None
    attempt_ids: list[str] = Field(default_factory=list)
    selected_attempt_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evaluation_result_id: str | None = None
    human_review_item_id: str | None = None
    reward_event_id: str | None = None
    status: RunStatus = RunStatus.PENDING
    current_node: str = "ingest_task"
    completed_nodes: list[str] = Field(default_factory=list)
    node_attempts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
    trace_id: str = Field(default_factory=new_trace_id)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    scratch: dict[str, Any] = Field(default_factory=dict)
