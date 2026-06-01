"""Context pack / item / retrieval schemas (charter §7.3, §10)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, computed_field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel, hash_payload


class ContextItem(ACPModel):
    id: str = Field(default_factory=lambda: new_id("citem"))
    kind: str  # file_chunk | symbol_chunk | test_chunk | doc_chunk | ...
    path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol_name: str | None = None
    content: str
    token_estimate: int = 0
    score: float = 0.0
    source: str = "retrieval"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def fingerprint(self) -> str:
        """Identity for dedupe / hashing: location + content."""
        return hash_payload(
            {
                "kind": self.kind,
                "path": self.path,
                "start_line": self.start_line,
                "end_line": self.end_line,
                "symbol_name": self.symbol_name,
                "content": self.content,
            }
        )


class RetrievalTrace(ACPModel):
    id: str = Field(default_factory=lambda: new_id("rtrace"))
    strategy: str
    query_terms: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    considered: int = 0
    selected: int = 0
    dropped: int = 0
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ContextPack(ACPModel):
    # Allow the computed ``content_hash`` to be ignored on re-validation.
    model_config = ConfigDict(extra="ignore", use_enum_values=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: new_id("pack"))
    repo_id: str
    task_id: str
    snapshot_id: str
    strategy: str = "hybrid_keyword_embedding"
    token_budget: int = 80_000
    token_estimate: int = 0
    items: list[ContextItem] = Field(default_factory=list)
    instructions: str = ""
    retrieval_trace: RetrievalTrace | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Deterministic hash of the content-bearing fields only.

        Excludes ``id`` and ``created_at`` so the same task/snapshot/strategy +
        item content always hashes identically (charter §10.5).
        """
        return hash_payload(
            {
                "repo_id": self.repo_id,
                "task_id": self.task_id,
                "snapshot_id": self.snapshot_id,
                "strategy": self.strategy,
                "token_budget": self.token_budget,
                "instructions": self.instructions,
                "items": [it.fingerprint() for it in self.items],
            }
        )

    def render_markdown(self) -> str:
        lines = [f"# Context pack ({self.strategy})", ""]
        if self.instructions:
            lines += ["## Instructions", self.instructions, ""]
        for it in self.items:
            loc = it.path
            if it.start_line is not None:
                loc += f":{it.start_line}-{it.end_line}"
            lines += [f"## {it.kind}: {loc}", "```", it.content, "```", ""]
        return "\n".join(lines)
