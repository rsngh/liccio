"""Run commands inside Docker (round-2 Block D).

`DockerCommandRunner` presents the same surface as `CommandRunner` but executes
each command inside the workspace's container (network-disabled, non-root,
resource-limited) via ``docker run``. The host-side ``docker`` invocation itself
goes through a mediated `CommandRunner` so timeouts/output capture/redaction
still apply. Untrusted/agent commands therefore never run as host subprocesses.
"""

from __future__ import annotations

from pathlib import Path

from acp.schemas.workspace import CommandRunRecord
from acp.workspaces.base import Workspace
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.docker import DockerWorkspaceManager


class DockerCommandRunner:
    def __init__(
        self,
        manager: DockerWorkspaceManager,
        workspace: Workspace,
        host_runner: CommandRunner | None = None,
        default_timeout_s: int = 120,
    ) -> None:
        self.manager = manager
        self.workspace = workspace
        # The host docker invocation runs from anywhere (cwd containment N/A) but
        # still through the mediated runner for capture + timeout.
        self.host = host_runner or CommandRunner(default_timeout_s=default_timeout_s)
        self.default_timeout_s = default_timeout_s

    def run(
        self,
        command: list[str],
        cwd: Path | str | None = None,
        timeout_s: int | None = None,
        attempt_id: str | None = None,
        trace_id: str | None = None,
        **_: object,
    ) -> CommandRunRecord:
        argv = self.manager.docker_run_argv(self.workspace, command)
        rec = self.host.run(
            argv,
            cwd=self.workspace.path,
            timeout_s=timeout_s or self.default_timeout_s,
            allow_cwd_outside_root=True,
            attempt_id=attempt_id,
            trace_id=trace_id,
        )
        # record the *logical* command (inside container), not the docker wrapper
        rec.argv = command
        rec.cwd = "/workspace"
        rec.resource_usage = {"backend": "docker", "image": self.manager.image}
        return rec
