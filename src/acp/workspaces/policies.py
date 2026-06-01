"""Workspace policy helpers (charter §9, §22)."""

from __future__ import annotations

from acp.schemas.workspace import WorkspacePolicy


def default_policy() -> WorkspacePolicy:
    return WorkspacePolicy(allow_network=False, cleanup="on_success", backend="local")


def strict_policy() -> WorkspacePolicy:
    return WorkspacePolicy(allow_network=False, cleanup="always", backend="local")
