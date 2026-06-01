"""Codex agent adapter (charter §12.5) — optional, experimental.

Detects a local Codex CLI / app-server. Treated as experimental: never required
by core tests. Healthcheck reports unavailable unless the `codex` binary is on
PATH.
"""

from __future__ import annotations

import shutil

from acp.core.enums import AgentKind, RunStatus
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
    DiffBundleRef,
)
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.workspaces.base import Workspace


class CodexAgentAdapter:
    kind = AgentKind.CODEX
    is_harness = False  # simple model adapter, not a full tool-loop harness

    def __init__(self, name: str = "codex", binary: str = "codex") -> None:
        self.name = name
        self.binary = binary

    def _available(self) -> bool:
        return shutil.which(self.binary) is not None

    async def healthcheck(self) -> AgentHealth:
        ok = self._available()
        return AgentHealth(
            name=self.name, kind=self.kind, available=ok,
            detail="ok" if ok else "codex binary not found on PATH",
        )

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan:
        return AgentPlan(summary=f"codex plan for {task.title}")

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        if not self._available():
            return AgentAttemptResult(status=RunStatus.FAILED, error="codex unavailable")
        # Real JSON-RPC/app-server integration is wired when a Codex server is
        # present; kept out of the core test path by design.
        return AgentAttemptResult(
            status=RunStatus.FAILED, error="codex execution not configured", wall_time_s=0.0
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.0)


# referenced for symmetry with other adapters' return types
_ = DiffBundleRef
