"""Deterministic fake agent adapter for tests (charter §12.2).

Modes:
  success_noop        - succeed, no diff
  fail_noop           - fail, no diff
  apply_patch_from_task_metadata - apply task.metadata['patch'] (unified diff)
  modify_file         - write task.metadata['modify'] = {path: content}
  break_tests         - introduce a failing change
  large_diff          - create many unrelated files (review-burden trigger)
  timeout             - simulate timeout -> TIMED_OUT
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

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
from acp.workspaces.diff import DiffCapturer


class FakeAgentAdapter:
    kind = AgentKind.FAKE

    def __init__(self, name: str = "fake", mode: str = "success_noop") -> None:
        self.name = name
        self.mode = mode

    async def healthcheck(self) -> AgentHealth:
        return AgentHealth(
            name=self.name, kind=self.kind, available=True, detail=f"mode={self.mode}"
        )

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan:
        return AgentPlan(summary=f"fake plan for {task.title}", steps=["edit", "test"])

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        mode = task.metadata.get("fake_mode", self.mode)
        root = Path(workspace.path)

        if mode == "timeout":
            await asyncio.sleep(0)
            return AgentAttemptResult(
                status=RunStatus.TIMED_OUT, wall_time_s=time.monotonic() - t0,
                error="simulated timeout",
            )
        if mode == "fail_noop":
            return AgentAttemptResult(
                status=RunStatus.FAILED,
                wall_time_s=time.monotonic() - t0,
                error="simulated failure",
            )
        if mode == "modify_file":
            for rel, content in (task.metadata.get("modify") or {}).items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
        elif mode == "break_tests":
            (root / "broken.py").write_text("def f():\n    raise RuntimeError('broken')\n")
        elif mode == "large_diff":
            for i in range(12):
                (root / f"unrelated_{i}.py").write_text(f"# noise file {i}\nX = {i}\n")
        elif mode == "apply_patch_from_task_metadata":
            # handled by PatchAgentAdapter normally; here just modify if provided
            for rel, content in (task.metadata.get("modify") or {}).items():
                (root / rel).write_text(content)

        diff = self._capture(workspace)
        return AgentAttemptResult(
            status=RunStatus.SUCCEEDED,
            diff=diff,
            input_token_count=100,
            output_token_count=50,
            estimated_cost_usd=0.0,
            wall_time_s=time.monotonic() - t0,
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="pass", score=1.0, confidence=0.5)

    @staticmethod
    def _capture(workspace: Workspace) -> DiffBundleRef:
        try:
            cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
            return DiffBundleRef(
                unified_diff=cap.get_unified_diff(), changed_files=cap.get_changed_files()
            )
        except Exception:  # noqa: BLE001 - no git or no base
            return DiffBundleRef()
