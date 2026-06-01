"""Pydantic v2 schemas — the wire/contract layer for acp."""

from __future__ import annotations

from acp.schemas.agent import (
    AgentAttempt,
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
    DiffBundleRef,
    ToolCallRecord,
)
from acp.schemas.base import ACPModel, hash_payload
from acp.schemas.context import ContextItem, ContextPack, RetrievalTrace
from acp.schemas.evaluation import (
    ActiveLearningScore,
    EvaluationResult,
    LLMJudgeResult,
    WeakLabel,
    WeakSignal,
)
from acp.schemas.human_review import HumanLabel, HumanReviewItem
from acp.schemas.learning import PolicyVersion, PostMergeOutcome, RewardEvent
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.routing import RoutingAction, RoutingDecision
from acp.schemas.task import Task, TaskClassification
from acp.schemas.trace import ArtifactRef, AuditEvent, SpanRecord
from acp.schemas.verification import Evidence, VerificationPlan, VerificationRun
from acp.schemas.workspace import (
    CommandRunRecord,
    DiffBundle,
    WorkspacePolicy,
    WorkspaceSpec,
)

# Resolve forward reference AgentAttemptResult.diff -> DiffBundleRef.
AgentAttemptResult.model_rebuild()

__all__ = [
    "ACPModel",
    "ActiveLearningScore",
    "AgentAttempt",
    "AgentAttemptResult",
    "AgentHealth",
    "AgentPlan",
    "AgentReviewResult",
    "ArtifactRef",
    "AuditEvent",
    "Budget",
    "CommandRunRecord",
    "ContextItem",
    "ContextPack",
    "DiffBundle",
    "DiffBundleRef",
    "Evidence",
    "EvaluationResult",
    "HumanLabel",
    "HumanReviewItem",
    "LLMJudgeResult",
    "PolicyVersion",
    "PostMergeOutcome",
    "RepoSnapshot",
    "Repository",
    "RetrievalTrace",
    "RewardEvent",
    "RoutingAction",
    "RoutingDecision",
    "SpanRecord",
    "Task",
    "TaskClassification",
    "ToolCallRecord",
    "VerificationPlan",
    "VerificationRun",
    "WeakLabel",
    "WeakSignal",
    "WorkspacePolicy",
    "WorkspaceSpec",
    "hash_payload",
]
