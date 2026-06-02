"""Registry of locally fine-tuned model artifacts (Alpha 8 WS7).

A :class:`ModelArtifact` records the identity, provenance, and metrics of a
locally trained adapter; :class:`ModelRegistry` is an in-memory index with an
optional on-disk JSON backing file. No heavy deps: importable without
torch/peft/transformers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from acp.core.time import isoformat, utcnow


@dataclass
class ModelArtifact:
    """A registered locally fine-tuned model/adapter."""

    id: str
    base_model: str
    dataset_kind: str
    adapter_path: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    metrics: dict[str, Any] = field(default_factory=dict)
    model_card_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serializable representation of the artifact."""
        data = asdict(self)
        data["created_at"] = isoformat(self.created_at)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelArtifact:
        """Reconstruct an artifact from :meth:`as_dict` output."""
        created = data.get("created_at")
        created_at = (
            datetime.fromisoformat(created)
            if isinstance(created, str)
            else (created or utcnow())
        )
        return cls(
            id=data["id"],
            base_model=data["base_model"],
            dataset_kind=data["dataset_kind"],
            adapter_path=data.get("adapter_path"),
            created_at=created_at,
            metrics=dict(data.get("metrics") or {}),
            model_card_ref=data.get("model_card_ref"),
        )


class ModelRegistry:
    """In-memory registry of :class:`ModelArtifact`, optionally JSON-backed."""

    def __init__(self, index_path: str | Path | None = None) -> None:
        self._index_path = Path(index_path) if index_path is not None else None
        self._artifacts: dict[str, ModelArtifact] = {}
        if self._index_path is not None and self._index_path.exists():
            self._load()

    def register(self, artifact: ModelArtifact) -> ModelArtifact:
        """Register (or replace) ``artifact`` by id; persist if JSON-backed."""
        self._artifacts[artifact.id] = artifact
        if self._index_path is not None:
            self._save()
        return artifact

    def get(self, artifact_id: str) -> ModelArtifact | None:
        """Return the artifact with ``artifact_id`` or None."""
        return self._artifacts.get(artifact_id)

    def list(self) -> list[ModelArtifact]:
        """All registered artifacts, newest first."""
        return sorted(
            self._artifacts.values(), key=lambda a: a.created_at, reverse=True
        )

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        assert self._index_path is not None
        raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        for entry in raw.get("artifacts", []):
            artifact = ModelArtifact.from_dict(entry)
            self._artifacts[artifact.id] = artifact

    def _save(self) -> None:
        assert self._index_path is not None
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"artifacts": [a.as_dict() for a in self.list()]}
        self._index_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
