"""Workspace spec, command runs, diffs (charter §7.3, §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class WorkspacePolicy(ACPModel):
    allow_network: bool = False
    cleanup: str = "on_success"  # always | never | on_success
    max_disk_mb: int | None = None
    backend: str = "local"  # local | docker | kubernetes | openhands
    memory_mb: int = 1024
    cpus: float = 1.0
    pids_limit: int = 256
    run_as_nonroot: bool = True


class WorkspaceSpec(ACPModel):
    id: str = Field(default_factory=lambda: new_id("ws"))
    repo_id: str
    snapshot_id: str
    base_commit: str
    path: str
    branch: str
    backend: str = "local"
    policy: WorkspacePolicy = Field(default_factory=WorkspacePolicy)
    initial_head: str | None = None
    final_head: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommandRunRecord(ACPModel):
    id: str = Field(default_factory=lambda: new_id("cmd"))
    attempt_id: str | None = None
    argv: list[str]
    cwd: str
    sanitized_env_keys: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    timed_out: bool = False
    allow_network: bool = False
    stdout_summary: str = ""
    stderr_summary: str = ""
    stdout_artifact_ref: str | None = None
    stderr_artifact_ref: str | None = None
    duration_s: float = 0.0
    resource_usage: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    trace_id: str | None = None


class DiffBundle(ACPModel):
    id: str = Field(default_factory=lambda: new_id("diff"))
    attempt_id: str | None = None
    base_commit: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    added_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    binary_files: list[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    unified_diff_ref: str | None = None
    unified_diff: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def is_empty(self) -> bool:
        return not self.changed_files and self.insertions == 0 and self.deletions == 0
