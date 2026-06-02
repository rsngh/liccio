"""Workspace manager factory (round-1 two-day D1B5).

Selects a backend (local/docker) by explicit name or by config, falling back to
local when an optional backend is unavailable.
"""

from __future__ import annotations

from pathlib import Path

from acp.core.config import ACPSettings, get_settings
from acp.workspaces.base import WorkspaceManager
from acp.workspaces.local import LocalWorkspaceManager


def make_workspace_manager(
    root: Path | str,
    backend: str | None = None,
    settings: ACPSettings | None = None,
) -> WorkspaceManager:
    settings = settings or get_settings()
    backend = backend or ("docker" if settings.enable_docker else "local")
    if backend == "docker":
        from acp.workspaces.docker import DockerWorkspaceManager, docker_available

        if docker_available():
            return DockerWorkspaceManager(
                root,
                image=settings.docker_image,
                memory_mb=settings.docker_memory_mb,
                cpus=settings.docker_cpus,
                pids_limit=settings.docker_pids_limit,
                network=settings.docker_network,
            )
        # graceful fallback
    return LocalWorkspaceManager(root)
