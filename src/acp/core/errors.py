"""Typed error hierarchy for the control plane."""

from __future__ import annotations


class ACPError(Exception):
    """Base class for all acp errors."""


class ConfigError(ACPError):
    """Invalid or missing configuration."""


class WorkspaceError(ACPError):
    """Workspace creation / git operation failure."""


class CommandSecurityError(ACPError):
    """A command violated a security/sandbox policy (e.g. cwd escape)."""


class CommandTimeout(ACPError):
    """A command exceeded its timeout."""


class ArtifactError(ACPError):
    """Artifact store failure (e.g. path traversal, checksum mismatch)."""


class AdapterUnavailable(ACPError):
    """An optional agent adapter / integration is not available."""


class PolicyViolation(ACPError):
    """A governance policy was violated."""


class NotFoundError(ACPError):
    """A requested entity does not exist."""
