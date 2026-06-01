"""Docker workspace manager (optional, charter §9).

Stub that reports unavailability unless the docker SDK and daemon are present.
Real container provisioning is wired in a later phase; kept behind the same
protocol so the orchestrator is backend-agnostic.
"""

from __future__ import annotations

from pathlib import Path

from acp.core.errors import AdapterUnavailable
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy
from acp.workspaces.base import Workspace


def docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:  # noqa: BLE001 - missing lib or no daemon
        return False


class DockerWorkspaceManager:
    backend = "docker"

    def __init__(self, root: Path | str, image: str = "python:3.11-slim") -> None:
        self.root = Path(root)
        self.image = image

    def create(
        self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy
    ) -> Workspace:
        if not docker_available():
            raise AdapterUnavailable("docker is not available")
        raise NotImplementedError("DockerWorkspaceManager provisioning lands in a later phase")

    def cleanup(self, workspace: Workspace) -> None:
        return None
