"""Shared Pydantic base for all acp schemas.

All schemas are Pydantic v2 models with:
- stable, canonical JSON serialization (sorted keys) for hashing,
- UTC-aware timestamps,
- forbidden extra fields (catch typos early).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict


class ACPModel(BaseModel):
    """Base model with canonical serialization helpers."""

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
        validate_assignment=True,
        ser_json_timedelta="float",
    )

    def canonical_json(self) -> str:
        """Deterministic JSON: sorted keys, no whitespace jitter."""
        data = self.model_dump(mode="json")
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)

    def compute_hash(self) -> str:
        """SHA256 of the canonical JSON representation."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def hash_payload(payload: Any) -> str:
    """SHA256 of an arbitrary JSON-serializable payload (sorted keys)."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
