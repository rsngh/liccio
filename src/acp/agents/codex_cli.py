"""Codex CLI vendor harness (alpha-7 WS8).

A capability-gated wrapper around the external ``codex`` command-line coding
agent. It is a *vendor harness*, not an ACP true harness: the CLI runs the agent
as a black box and we normalize the run into the standard
:class:`AgentAttemptResult` + :class:`~acp.schemas.trace.AgentTrace` surface that
the in-process harnesses (``openai_harness`` / ``claude_harness``) produce.

The shim drives a single, non-interactive (headless) ``codex`` invocation against
the workspace path under the mediated :class:`CommandRunner` (timeout,
output truncation, secret scrub, cwd containment), captures the invocation as a
``run_command`` tool/command record, captures the resulting git diff via the
workspace's :class:`DiffCapturer`, records wall time, and derives status:
``SUCCEEDED`` when the command exits 0 *and* produced a diff, else ``FAILED``
(``TIMED_OUT`` on a wall-time/timeout cap).

It requires a ``codex`` binary on ``PATH``. Without it the adapter degrades
cleanly: ``healthcheck`` reports unavailable and ``execute`` returns a clean
unavailable result rather than raising. The invocation is defensive — codex CLI
flags vary across versions, so the argv is built conservatively and any nonzero
exit / timeout / exception is turned into a clean ``FAILED`` result; ``execute``
never raises.

As a harness (``is_harness=True``) it inherits the Docker-required execution
backend governance via :meth:`PolicyEngine.required_backend`; this shim does not
bypass it.
"""

from __future__ import annotations

import time
from pathlib import Path

from acp.agents.vendor_base import VendorCapability, VendorHarnessAdapter
from acp.core.enums import AgentKind, RunStatus
from acp.schemas.agent import AgentAttemptResult, Budget, DiffBundleRef, ToolCallRecord
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.diff import DiffCapturer

# Hard cap on vendor invocations per execute() call. A single headless codex run
# does the work; the cap is a defensive guard against accidental loops.
MAX_INVOCATIONS = 1


class CodexCLIAdapter(VendorHarnessAdapter):
    """Vendor harness that drives the ``codex`` CLI as a black-box coding agent."""

    kind = AgentKind.CODEX
    capability = VendorCapability(kind="cli", requirement="codex")

    def __init__(
        self,
        name: str = "codex_cli",
        model: str = "codex",
        max_invocations: int = MAX_INVOCATIONS,
    ) -> None:
        super().__init__(name=name, model=model)
        self.max_invocations = max_invocations

    # --- argv construction ----------------------------------------------------
    def build_command(self, task: Task, context_pack: ContextPack, workspace) -> list[str]:
        """Build a conservative, non-interactive ``codex`` argv for ``workspace``.

        ``codex exec`` runs the agent headlessly (no TUI); ``--cd`` scopes it to
        the workspace path. Flags vary across codex versions, so we keep the argv
        minimal and pass the task as the trailing prompt argument.
        """
        prompt = f"{task.title}\n\n{task.body}"
        ws_path = str(Path(workspace.path).resolve())
        return [
            self.capability.requirement,
            "exec",
            # ``codex exec`` defaults to a READ-ONLY sandbox, so the agent can plan
            # but never edits files. Grant workspace-write so it can actually apply
            # its fix (writes stay scoped to the workspace dir).
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--cd",
            ws_path,
            prompt,
        ]

    def _make_runner(self, workspace) -> CommandRunner:
        return CommandRunner(allowed_root=Path(workspace.path), scrub_secrets=True)

    # --- execution ------------------------------------------------------------
    async def execute(
        self, task: Task, context_pack: ContextPack, workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        if not self.available():
            return AgentAttemptResult(
                status=RunStatus.FAILED,
                error=f"vendor harness unavailable: {self._unavailable_detail()}",
                wall_time_s=time.monotonic() - t0,
                metadata={"category": self.category, "available": False},
            )

        # The codex run goes through a dedicated CommandRunner so we capture it as
        # one mediated command record (trace parity with the in-process harnesses).
        session_id = f"sess_{int(t0 * 1000)}"
        command = self.build_command(task, context_pack, workspace)
        runner = self._make_runner(workspace)

        if self.max_invocations < 1:
            return self._finalize(
                workspace=workspace, t0=t0, session_id=session_id,
                tool_calls=[], exit_code=None,
                error="budget_exceeded:invocations", invocations=0,
            )

        # Single headless invocation under a wall-time timeout from the budget.
        timeout_s = max(1, int(budget.max_wall_time_s))
        error: str | None = None
        exit_code: int | None = None
        try:
            rec = runner.run(
                command,
                cwd=Path(workspace.path).resolve(),
                timeout_s=timeout_s,
            )
            exit_code = rec.exit_code
            if rec.timed_out:
                error = "timeout"
            elif exit_code not in (0, None):
                summary = (rec.stderr_summary or rec.stdout_summary or "").strip()
                error = f"codex exited {exit_code}: {summary[:200]}".strip()
        except Exception as exc:  # noqa: BLE001 - structured failure, never raise out
            error = str(exc)

        summary = f"exit={exit_code} codex headless run"
        tool_calls = [
            ToolCallRecord(
                tool_name="run_command",
                arguments={"command": command},
                result_summary=summary,
                error=error,
            )
        ]
        return self._finalize(
            workspace=workspace, t0=t0, session_id=session_id,
            tool_calls=tool_calls, exit_code=exit_code, error=error, invocations=1,
        )

    def _finalize(
        self, *, workspace, t0: float, session_id: str,
        tool_calls: list[ToolCallRecord], exit_code: int | None,
        error: str | None, invocations: int,
    ) -> AgentAttemptResult:
        """Capture the workspace diff and derive normalized status."""
        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        changed_files = cap.get_changed_files()
        unified_diff = cap.get_unified_diff()
        produced_diff = bool(changed_files)

        if error in ("timeout", "budget_exceeded:wall"):
            status = RunStatus.TIMED_OUT
        elif exit_code == 0 and produced_diff and error is None:
            status = RunStatus.SUCCEEDED
        else:
            status = RunStatus.FAILED
            if error is None and exit_code == 0 and not produced_diff:
                error = "codex produced no diff"

        return AgentAttemptResult(
            status=status,
            diff=DiffBundleRef(unified_diff=unified_diff, changed_files=changed_files),
            wall_time_s=time.monotonic() - t0,
            tool_calls=tool_calls,
            error=error,
            metadata={
                "category": self.category,
                "session_id": session_id,
                "is_harness": self.is_harness,
                "invocations": invocations,
                "exit_code": exit_code,
                "changed_files": changed_files,
            },
        )
