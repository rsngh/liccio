"""Routing policy protocol + PolicyDecision (charter §13.3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from acp.core.enums import ExplorationMode
from acp.schemas.base import ACPModel
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction


class PolicyDecision(ACPModel):
    policy_version: str
    action: RoutingAction
    action_probability: float = Field(gt=0.0, le=1.0)
    context_key: str = "global"
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    exploration_mode: ExplorationMode = ExplorationMode.EXPLOIT
    exploration_reason: str = ""
    seed: int = 1234


@runtime_checkable
class RoutingPolicy(Protocol):
    policy_version: str

    def choose_action(
        self, features: dict, candidates: list[RoutingAction]
    ) -> PolicyDecision: ...

    def observe_reward(self, decision: PolicyDecision, reward: RewardEvent) -> None: ...
