"""Optional LoRA smoke-training entrypoint (Alpha-7 WS18).

This module imports cleanly without ``torch``/``peft``/``transformers``: the
heavy deps are probed lazily via :func:`acp.core.optional.try_import`. Use
:func:`available` to gate; :func:`run_smoke` raises a clear error when the deps
are missing rather than crashing at import time. It never requires a GPU or
real training in tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acp.core.optional import try_import

_REQUIRED = ("torch", "transformers", "peft", "datasets")


class TrainingDepsUnavailable(RuntimeError):
    """Raised when LoRA training dependencies are not installed."""


def missing_deps() -> list[str]:
    """Names of required training deps that cannot be imported."""
    return [name for name in _REQUIRED if try_import(name) is None]


def available() -> bool:
    """True iff every LoRA training dependency is importable."""
    return not missing_deps()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def run_smoke(
    dataset_path: str | Path,
    out_dir: str | Path,
    *,
    max_steps: int = 1,
) -> dict[str, Any]:
    """Run a minimal LoRA smoke fine-tune over ``dataset_path``.

    Raises :class:`TrainingDepsUnavailable` (a clear "training deps unavailable"
    error) when torch/peft/transformers/datasets are not installed.
    """
    missing = missing_deps()
    if missing:
        raise TrainingDepsUnavailable(
            "training deps unavailable: install "
            + ", ".join(missing)
            + " to run the LoRA smoke entrypoint"
        )

    ds_path = Path(dataset_path)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    rows = _load_jsonl(ds_path)

    # Heavy imports are deferred until after the availability gate so the module
    # stays importable without these packages.
    torch = try_import("torch")
    transformers = try_import("transformers")
    peft = try_import("peft")
    assert torch is not None and transformers is not None and peft is not None

    # Intentionally minimal: a real trainer is wired by the parent when deps and
    # hardware are present. We surface enough to confirm the path is reachable.
    return {
        "status": "ready",
        "n_examples": len(rows),
        "out_dir": str(out_path),
        "max_steps": max_steps,
    }
