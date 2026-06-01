"""Workspace manager protocol and shared types (charter §9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy, WorkspaceSpec


@dataclass
class Workspace:
    """A live workspace handle."""

    spec: WorkspaceSpec
    path: Path
    backend: str = "local"
    metadata: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class WorkspaceManager(Protocol):
    backend: str

    def create(
        self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy
    ) -> Workspace: ...

    def cleanup(self, workspace: Workspace) -> None: ...
