"""Agent adapter protocol (charter §12.1)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from acp.core.enums import AgentKind
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
)
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.workspaces.base import Workspace


@runtime_checkable
class AgentAdapter(Protocol):
    name: str
    kind: AgentKind

    async def healthcheck(self) -> AgentHealth: ...

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan: ...

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult: ...

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult: ...
