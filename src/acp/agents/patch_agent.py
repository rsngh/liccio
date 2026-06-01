"""Deterministic patch-applying adapter (charter §12.3).

Applies a patch defined in task metadata, enabling full end-to-end tests with no
LLM. Two patch forms are supported:
  - task.metadata['files'] = {path: new_content}  (preferred, robust)
  - task.metadata['patch'] = "<unified diff>"      (applied via `git apply`)
"""

from __future__ import annotations

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
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.diff import DiffCapturer


class PatchAgentAdapter:
    kind = AgentKind.PATCH

    def __init__(self, name: str = "patch", runner: CommandRunner | None = None) -> None:
        self.name = name
        self.runner = runner

    async def healthcheck(self) -> AgentHealth:
        return AgentHealth(name=self.name, kind=self.kind, available=True)

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan:
        files = list((task.metadata.get("files") or {}).keys())
        return AgentPlan(summary="apply deterministic patch", steps=[f"write {f}" for f in files])

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        root = Path(workspace.path)
        try:
            files = task.metadata.get("files")
            if files:
                for rel, content in files.items():
                    target = root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
            elif task.metadata.get("patch"):
                runner = self.runner or CommandRunner(allowed_root=root)
                patch_file = root / ".acp_patch.diff"
                patch_file.write_text(task.metadata["patch"])
                rec = runner.run(
                    ["git", "apply", str(patch_file)], cwd=root, allow_cwd_outside_root=True
                )
                patch_file.unlink(missing_ok=True)
                if rec.exit_code not in (0, None):
                    return AgentAttemptResult(
                        status=RunStatus.FAILED,
                        wall_time_s=time.monotonic() - t0,
                        error=f"git apply failed: {rec.stderr_summary[:500]}",
                    )
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            return AgentAttemptResult(
                status=RunStatus.FAILED, wall_time_s=time.monotonic() - t0, error=str(exc)
            )

        cap = DiffCapturer(str(root), workspace.spec.base_commit)
        return AgentAttemptResult(
            status=RunStatus.SUCCEEDED,
            diff=DiffBundleRef(
                unified_diff=cap.get_unified_diff(), changed_files=cap.get_changed_files()
            ),
            wall_time_s=time.monotonic() - t0,
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="pass", score=1.0, confidence=0.6)
