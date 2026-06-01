"""Routing action / decision schemas (charter §7.3, §13)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from acp.core.enums import AgentKind, ExplorationMode
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class RoutingAction(ACPModel):
    agent_kind: AgentKind
    agent_name: str
    model_name: str | None = None
    context_strategy: str = "hybrid_keyword_embedding"
    context_token_budget: int = 80_000
    tool_permissions: list[str] = Field(default_factory=list)
    workspace_policy: str = "local"
    verification_policy: str = "standard"
    max_cost_usd: float = 5.0
    max_wall_time_s: int = 600
    parallelism: int = 1
    fallback_policy: str | None = None
    requires_human_approval: bool = False

    def key(self) -> str:
        """Stable identity of the action arm (for bandit indexing)."""
        return "|".join(
            [
                self.agent_kind if isinstance(self.agent_kind, str) else self.agent_kind.value,
                self.agent_name,
                self.model_name or "-",
                self.context_strategy,
                self.verification_policy,
            ]
        )


class RoutingDecision(ACPModel):
    id: str = Field(default_factory=lambda: new_id("route"))
    task_id: str
    snapshot_id: str | None = None
    policy_version: str
    action: RoutingAction
    action_probability: float = Field(gt=0.0, le=1.0)
    candidate_actions: list[RoutingAction] = Field(default_factory=list)
    model_scores: dict[str, float] = Field(default_factory=dict)
    exploration_mode: ExplorationMode = ExplorationMode.EXPLOIT
    exploration_reason: str = ""
    constraints_applied: list[str] = Field(default_factory=list)
    feature_hash: str = ""
    seed: int = 1234
    created_at: datetime = Field(default_factory=utcnow)
