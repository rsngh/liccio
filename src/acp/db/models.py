"""SQLAlchemy ORM models (charter §8.1).

Each table carries a few queryable columns (id, foreign keys, trace_id, status,
created_at) plus a ``data`` JSON column holding the full Pydantic payload. This
gives both efficient queries (by task_id / trace_id) and lossless round-trips.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from acp.db.base import Base


class _Row(Base):
    """Abstract base with columns common to every entity table."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Repository(_Row):
    __tablename__ = "repositories"


class RepoSnapshot(_Row):
    __tablename__ = "repo_snapshots"
    repo_id: Mapped[str] = mapped_column(String, index=True)


class Task(_Row):
    __tablename__ = "tasks"
    repo_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class ContextPack(_Row):
    __tablename__ = "context_packs"
    task_id: Mapped[str] = mapped_column(String, index=True)
    repo_id: Mapped[str] = mapped_column(String, index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class ContextItem(_Row):
    __tablename__ = "context_items"
    pack_id: Mapped[str] = mapped_column(String, index=True)


class RoutingDecision(_Row):
    __tablename__ = "routing_decisions"
    task_id: Mapped[str] = mapped_column(String, index=True)
    policy_version: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class AgentAttempt(_Row):
    __tablename__ = "agent_attempts"
    task_id: Mapped[str] = mapped_column(String, index=True)
    routing_decision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class ToolCall(_Row):
    __tablename__ = "tool_calls"
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class CommandRun(_Row):
    __tablename__ = "command_runs"
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class DiffBundle(_Row):
    __tablename__ = "diff_bundles"
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class VerificationPlan(_Row):
    __tablename__ = "verification_plans"
    task_id: Mapped[str] = mapped_column(String, index=True)


class VerificationRun(_Row):
    __tablename__ = "verification_runs"
    task_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class Evidence(_Row):
    __tablename__ = "evidence"
    task_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    verification_run_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class EvaluationResult(_Row):
    __tablename__ = "evaluation_results"
    task_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class HumanReviewItem(_Row):
    __tablename__ = "human_review_items"
    task_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class HumanLabel(_Row):
    __tablename__ = "human_labels"
    review_item_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)


class WeakLabel(_Row):
    __tablename__ = "weak_labels"
    task_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class RewardEvent(_Row):
    __tablename__ = "reward_events"
    task_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    routing_decision_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class PolicyVersion(_Row):
    __tablename__ = "policy_versions"
    name: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class PostMergeOutcome(_Row):
    __tablename__ = "post_merge_outcomes"
    task_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


class Artifact(_Row):
    __tablename__ = "artifacts"


class AuditLog(_Row):
    __tablename__ = "audit_log"
    trace_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String, index=True, nullable=True)


# Composite index for the common "all records for a trace" query.
Index("ix_attempt_task_status", AgentAttempt.task_id, AgentAttempt.status)

ALL_MODELS = [
    Repository,
    RepoSnapshot,
    Task,
    ContextPack,
    ContextItem,
    RoutingDecision,
    AgentAttempt,
    ToolCall,
    CommandRun,
    DiffBundle,
    VerificationPlan,
    VerificationRun,
    Evidence,
    EvaluationResult,
    HumanReviewItem,
    HumanLabel,
    WeakLabel,
    RewardEvent,
    PolicyVersion,
    PostMergeOutcome,
    Artifact,
    AuditLog,
]
