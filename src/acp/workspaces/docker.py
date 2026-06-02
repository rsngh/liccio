"""Docker workspace manager v1 (charter §9; round-1 two-day D1B5).

Uses the ``docker`` CLI (no SDK dependency). Each workspace is a local git
worktree mounted read-write into a throwaway container; commands run inside the
container with network disabled, non-root user, and memory/cpu/pids limits.
When Docker is unavailable the manager raises ``AdapterUnavailable`` and the
workflow falls back to the local backend.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from git import Repo

from acp.core.errors import AdapterUnavailable, WorkspaceError
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy, WorkspaceSpec
from acp.workspaces.base import Workspace
from acp.workspaces.diff import DiffCapturer
from acp.workspaces.git_ops import add_worktree, is_dirty, remove_worktree


def docker_available() -> bool:
    """True when the docker CLI exists and the daemon responds."""
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(  # noqa: S603,S607
            ["docker", "info"], capture_output=True, timeout=10
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


class DockerWorkspaceManager:
    backend = "docker"

    def __init__(
        self,
        root: Path | str,
        image: str = "python:3.11-slim",
        memory_mb: int = 1024,
        cpus: float = 1.0,
        pids_limit: int = 256,
        network: str = "bridge",
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.image = image
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.pids_limit = pids_limit
        # Network used when a workspace policy allows networking; "none" keeps the
        # sandbox isolated even when the policy would otherwise permit egress.
        self.network = network

    def create(
        self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy
    ) -> Workspace:
        if not docker_available():
            raise AdapterUnavailable("docker CLI/daemon not available")
        if not repo.local_path or not (Path(repo.local_path) / ".git").exists():
            raise WorkspaceError(f"repo {repo.id} is not a local git repository")
        ws_id = f"dws_{uuid.uuid4().hex[:12]}"
        ws_path = self.root / ws_id
        branch = f"acp/{ws_id}"
        add_worktree(repo.local_path, ws_path, snapshot.base_commit, branch)
        head = Repo(ws_path).head.commit.hexsha
        spec = WorkspaceSpec(
            id=ws_id, repo_id=repo.id, snapshot_id=snapshot.id,
            base_commit=snapshot.base_commit, path=str(ws_path), branch=branch,
            backend=self.backend, policy=policy, initial_head=head,
            metadata={"image": self.image, "network": str(policy.allow_network).lower()},
        )
        return Workspace(spec=spec, path=ws_path, backend=self.backend,
                         metadata={"source_repo": str(repo.local_path)})

    def docker_run_argv(self, workspace: Workspace, command: list[str]) -> list[str]:
        """Build the ``docker run`` argv that executes ``command`` in the sandbox."""
        policy = workspace.spec.policy
        argv = [
            "docker", "run", "--rm",
            "--network", self.network if policy.allow_network else "none",
            "-m", f"{policy.memory_mb or self.memory_mb}m",
            "--cpus", str(policy.cpus or self.cpus),
            "--pids-limit", str(policy.pids_limit or self.pids_limit),
            "-v", f"{workspace.path}:/workspace",
            "-w", "/workspace",
        ]
        if policy.run_as_nonroot:
            argv += ["-u", "1000:1000"]
        argv += [self.image, *command]
        return argv

    # ---- workspace observation -------------------------------------------
    # The worktree is a host directory mounted read-write into the container, so
    # git observation runs on the host against the same files the container saw.

    def capture_diff(self, workspace: Workspace, attempt_id: str | None = None):
        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        return cap.build_bundle(attempt_id=attempt_id)

    def dirty(self, workspace: Workspace) -> bool:
        return is_dirty(workspace.path)

    def final_head(self, workspace: Workspace) -> str:
        return Repo(workspace.path).head.commit.hexsha

    def cleanup(self, workspace: Workspace, *, succeeded: bool = True) -> None:
        policy = workspace.spec.policy.cleanup
        if policy == "never" or (policy == "on_success" and not succeeded):
            return
        source = workspace.metadata.get("source_repo")
        if source:
            remove_worktree(source, workspace.path)
        else:
            shutil.rmtree(workspace.path, ignore_errors=True)
