"""Repository and snapshot schemas (charter §7.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class Repository(ACPModel):
    id: str = Field(default_factory=lambda: new_id("repo"))
    name: str
    url: str | None = None
    default_branch: str = "main"
    local_path: str | None = None
    provider: str = "local"  # local | github | gitlab | ...
    visibility: str = "private"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepoSnapshot(ACPModel):
    id: str = Field(default_factory=lambda: new_id("snap"))
    repo_id: str
    base_commit: str
    branch: str = "main"
    dirty: bool = False
    language_summary: dict[str, int] = Field(default_factory=dict)
    index_version: int = 1
    index_hash: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
