"""OpenHands agent adapter (charter §12.6) — optional, lazy.

Lazy-imports ``openhands`` SDK and/or uses an Agent Server URL. Reports
unavailable when neither is configured.
"""

from __future__ import annotations

from acp.core.enums import AgentKind, RunStatus
from acp.core.optional import try_import
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


class OpenHandsAgentAdapter:
    kind = AgentKind.OPENHANDS
    is_harness = False  # simple model adapter, not a full tool-loop harness

    def __init__(self, name: str = "openhands", server_url: str | None = None) -> None:
        self.name = name
        self.server_url = server_url

    def _available(self) -> bool:
        return try_import("openhands") is not None or self.server_url is not None

    async def healthcheck(self) -> AgentHealth:
        ok = self._available()
        return AgentHealth(
            name=self.name, kind=self.kind, available=ok,
            detail="ok" if ok else "openhands SDK / server URL not configured",
        )

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan:
        return AgentPlan(summary=f"openhands plan for {task.title}")

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        if not self._available():
            return AgentAttemptResult(status=RunStatus.FAILED, error="openhands unavailable")
        return AgentAttemptResult(
            status=RunStatus.FAILED, error="openhands execution not configured"
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.0)
