"""Kubernetes workspace manager (optional stub, charter §9)."""

from __future__ import annotations

from pathlib import Path

from acp.core.errors import AdapterUnavailable
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy
from acp.workspaces.base import Workspace


class KubernetesWorkspaceManager:
    backend = "kubernetes"

    def __init__(self, root: Path | str, namespace: str = "acp") -> None:
        self.root = Path(root)
        self.namespace = namespace

    def create(
        self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy
    ) -> Workspace:
        raise AdapterUnavailable("kubernetes workspace backend is not configured")

    def cleanup(self, workspace: Workspace) -> None:
        return None
