"""Training-data factory schemas (Alpha-7 WS3/4/18).

These models describe the *exhaust* of ACP runs distilled into versioned,
redacted, leakage-audited training datasets. A ``TrainingExample`` is a single
distilled supervision example; a ``DatasetVersion`` is an immutable, hashed
snapshot of a built dataset together with its build config and a model card.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class TrainingExample(ACPModel):
    """A single distilled supervision example derived from run exhaust."""

    id: str = Field(default_factory=lambda: new_id("trex"))
    dataset_kind: str
    task_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    target: Any = None
    label_source: str = "objective"  # objective | weak | human | derived
    split: str = "train"  # train | test | holdout
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    def content_hash(self) -> str:
        """Hash of the supervision content (kind + inputs + target).

        Identity excludes ``id``/``created_at`` so duplicate examples distilled
        from different runs collapse during deduplication.
        """
        from acp.schemas.base import hash_payload

        return hash_payload(
            {
                "dataset_kind": self.dataset_kind,
                "inputs": self.inputs,
                "target": self.target,
            }
        )


class DatasetSplit(ACPModel):
    """Membership of a single split within a dataset version."""

    name: str  # train | test | holdout
    n_examples: int = 0
    example_ids: list[str] = Field(default_factory=list)


class DatasetBuildConfig(ACPModel):
    """Deterministic configuration that produced a dataset version."""

    kind: str
    temporal_split_at: datetime | None = None
    repo_holdout: list[str] = Field(default_factory=list)
    test_fraction: float = Field(default=0.2, ge=0.0, le=1.0)
    dedup: bool = True
    redact: bool = True
    drop_generated_files: bool = True
    min_label_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    seed: int = 1234


class RedactionReport(ACPModel):
    """Summary of secret scrubbing applied while building a dataset."""

    examples_scanned: int = 0
    examples_modified: int = 0
    secrets_redacted: int = 0
    redactor_value_patterns: int = 0


class LeakageAudit(ACPModel):
    """Result of scanning built examples for surviving secrets / leakage."""

    examples_scanned: int = 0
    secret_survivors: int = 0
    train_test_id_overlap: int = 0
    repo_holdout_violations: int = 0
    clean: bool = True
    findings: list[str] = Field(default_factory=list)


class DatasetCard(ACPModel):
    """Human-readable provenance + composition card for a dataset version."""

    kind: str
    description: str = ""
    n_examples: int = 0
    label_sources: dict[str, int] = Field(default_factory=dict)
    splits: dict[str, int] = Field(default_factory=dict)
    source_tasks: int = 0
    redaction: RedactionReport = Field(default_factory=RedactionReport)
    leakage: LeakageAudit = Field(default_factory=LeakageAudit)
    notes: list[str] = Field(default_factory=list)


class DatasetVersion(ACPModel):
    """Immutable, hashed snapshot of a built dataset."""

    id: str = Field(default_factory=lambda: new_id("dset"))
    kind: str
    version: str
    n_examples: int = 0
    splits: dict[str, int] = Field(default_factory=dict)
    build_config: dict[str, Any] = Field(default_factory=dict)
    card: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
