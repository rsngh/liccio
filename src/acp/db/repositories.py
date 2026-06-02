"""Persistence layer mapping Pydantic schemas <-> ORM rows.

A single ``EntityStore`` handles all entity types via a registry that links each
Pydantic schema class to its ORM table. Indexed columns are auto-populated by
matching ORM column names against fields in the schema's JSON dump; the full
payload is stored in ``data`` for lossless reconstruction.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from acp.db import models as m
from acp.schemas import (
    AgentAttempt,
    ArtifactRef,
    AuditEvent,
    CommandRunRecord,
    ContextItem,
    ContextPack,
    DiffBundle,
    EvaluationResult,
    Evidence,
    HumanLabel,
    HumanReviewItem,
    PolicyVersion,
    PostMergeOutcome,
    Repository,
    RepoSnapshot,
    RewardEvent,
    RoutingDecision,
    SpanRecord,
    Task,
    ToolCallRecord,
    VerificationPlan,
    VerificationRun,
    WeakLabel,
)
from acp.schemas.base import ACPModel
from acp.schemas.eval import EvalCase, EvalMetric, EvalReport, EvalRun
from acp.schemas.learning import PolicyState
from acp.schemas.trace import AgentTrace
from acp.schemas.viability import ViabilityAssessment

S = TypeVar("S", bound=ACPModel)

# schema class -> ORM model
_REGISTRY: dict[type[ACPModel], type[m._Row]] = {
    Repository: m.Repository,
    RepoSnapshot: m.RepoSnapshot,
    Task: m.Task,
    ContextPack: m.ContextPack,
    ContextItem: m.ContextItem,
    RoutingDecision: m.RoutingDecision,
    AgentAttempt: m.AgentAttempt,
    ToolCallRecord: m.ToolCall,
    CommandRunRecord: m.CommandRun,
    DiffBundle: m.DiffBundle,
    VerificationPlan: m.VerificationPlan,
    VerificationRun: m.VerificationRun,
    Evidence: m.Evidence,
    EvaluationResult: m.EvaluationResult,
    HumanReviewItem: m.HumanReviewItem,
    HumanLabel: m.HumanLabel,
    WeakLabel: m.WeakLabel,
    RewardEvent: m.RewardEvent,
    PolicyVersion: m.PolicyVersion,
    PostMergeOutcome: m.PostMergeOutcome,
    ArtifactRef: m.Artifact,
    AuditEvent: m.AuditLog,
    SpanRecord: m.Span,
    EvalRun: m.EvalRun,
    EvalCase: m.EvalCase,
    EvalMetric: m.EvalMetric,
    EvalReport: m.EvalReport,
    PolicyState: m.PolicyState,
    AgentTrace: m.AgentTraceRow,
    ViabilityAssessment: m.ViabilityAssessmentRow,
}


def _orm_columns(orm_cls: type[m._Row]) -> set[str]:
    return {c.key for c in inspect(orm_cls).columns}


class EntityStore:
    """Generic CRUD over all acp entities within a Session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _orm_for(self, schema: ACPModel) -> type[m._Row]:
        orm = _REGISTRY.get(type(schema))
        if orm is None:
            raise KeyError(f"no ORM mapping for {type(schema).__name__}")
        return orm

    def save(self, schema: S, *, extra_index: dict[str, Any] | None = None) -> S:
        orm_cls = self._orm_for(schema)
        payload = schema.model_dump(mode="json")
        cols = _orm_columns(orm_cls)
        row_kwargs: dict[str, Any] = {"id": payload["id"], "data": payload}
        if "created_at" in cols and "created_at" in payload:
            row_kwargs["created_at"] = getattr(schema, "created_at", None)
        for col in cols - {"id", "data", "created_at"}:
            if extra_index and col in extra_index:
                row_kwargs[col] = extra_index[col]
            elif col in payload:
                row_kwargs[col] = payload[col]
        row = self.session.get(orm_cls, payload["id"])
        if row is None:
            row = orm_cls(**row_kwargs)
            self.session.add(row)
        else:
            for k, v in row_kwargs.items():
                setattr(row, k, v)
        return schema

    def get(self, schema_cls: type[S], entity_id: str) -> S | None:
        orm_cls = _REGISTRY[schema_cls]
        row = self.session.get(orm_cls, entity_id)
        if row is None:
            return None
        return schema_cls.model_validate(row.data)

    def list_by(self, schema_cls: type[S], **filters: Any) -> list[S]:
        orm_cls = _REGISTRY[schema_cls]
        stmt = select(orm_cls)
        for k, v in filters.items():
            stmt = stmt.where(getattr(orm_cls, k) == v)
        rows = self.session.execute(stmt).scalars().all()
        return [schema_cls.model_validate(r.data) for r in rows]

    def all_for_task(self, task_id: str) -> dict[str, list[ACPModel]]:
        """Every child record referencing a task_id (charter §8.2)."""
        out: dict[str, list[ACPModel]] = {}
        for schema_cls, orm_cls in _REGISTRY.items():
            if "task_id" not in _orm_columns(orm_cls):
                continue
            rows = self.list_by(schema_cls, task_id=task_id)
            if rows:
                out[schema_cls.__name__] = list(rows)
        return out

    def all_for_trace(self, trace_id: str) -> dict[str, list[ACPModel]]:
        out: dict[str, list[ACPModel]] = {}
        for schema_cls, orm_cls in _REGISTRY.items():
            if "trace_id" not in _orm_columns(orm_cls):
                continue
            rows = self.list_by(schema_cls, trace_id=trace_id)
            if rows:
                out[schema_cls.__name__] = list(rows)
        return out
