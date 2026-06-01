"""Helper for lazy optional-dependency imports."""

from __future__ import annotations

import importlib
from types import ModuleType


def try_import(module: str) -> ModuleType | None:
    """Import a module, returning None if it (or its deps) are unavailable."""
    try:
        return importlib.import_module(module)
    except Exception:  # noqa: BLE001 - any import-time failure -> unavailable
        return None
