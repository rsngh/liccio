"""ID generation. Prefixed, sortable-ish, URL-safe identifiers."""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Generate a new prefixed id, e.g. ``task_3f9a...``.

    Uses uuid4 hex (random). For deterministic tests, pass seeded ids explicitly
    rather than relying on this function.
    """
    return f"{prefix}_{uuid.uuid4().hex}"


def new_trace_id() -> str:
    return uuid.uuid4().hex
