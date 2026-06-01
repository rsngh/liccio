"""Reward, policy version, post-merge outcome (charter §7.3, §16)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from acp.core.enums import PolicyStatus
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class RewardEvent(ACPModel):
    id: str = Field(default_factory=lambda: new_id("reward"))
    task_id: str
    attempt_id: str | None = None
    routing_decision_id: str | None = None
    policy_version: str | None = None
    reward: float
    components: dict[str, float] = Field(default_factory=dict)
    label_source: str = "objective"  # objective | weak | human | post_merge
    created_at: datetime = Field(default_factory=utcnow)
    matured_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _components_explain_reward(self) -> RewardEvent:
        """A reward must store components that explain it (charter §7.3, §16.1).

        Either the components sum (approximately) to the reward, or metadata
        carries an explicit explanation. This prevents opaque scalar rewards.
        """
        if self.components:
            return self
        if "reward_explanation" in self.metadata:
            return self
        raise ValueError(
            "RewardEvent requires non-empty `components` or "
            "`metadata['reward_explanation']` to explain the reward"
        )


class PolicyVersion(ACPModel):
    id: str = Field(default_factory=lambda: new_id("policy"))
    name: str
    version: str
    kind: str = "heuristic"  # heuristic | bandit | supervised
    status: PolicyStatus = PolicyStatus.DRAFT
    params: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: str | None = None
    traffic_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    parent_version: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyState(ACPModel):
    """Persisted bandit state so routing learns across process restarts (R2-J)."""

    id: str = Field(default_factory=lambda: new_id("pstate"))
    policy_version: str
    arms: dict[str, Any] = Field(default_factory=dict)  # ctx -> arm_key -> stats
    metrics: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utcnow)


class PostMergeOutcome(ACPModel):
    id: str = Field(default_factory=lambda: new_id("outcome"))
    task_id: str
    attempt_id: str | None = None
    merged: bool = False
    merge_time: datetime | None = None
    review_comments_count: int = 0
    review_rounds: int = 0
    reverted: bool = False
    revert_time: datetime | None = None
    incident_link: str | None = None
    issue_reopened: bool = False
    followup_bug_created: bool = False
    human_satisfaction_score: float | None = None
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
