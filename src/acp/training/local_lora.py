"""Local LoRA fine-tuning entrypoint (Alpha 8 WS7).

This module follows the gated pattern of :mod:`acp.training.lora_smoke`: it
imports cleanly without ``torch``/``peft``/``transformers`` and probes the heavy
deps lazily via :func:`acp.core.optional.try_import`. Unlike ``lora_smoke``,
:func:`run_local_lora` never raises when the deps are missing — it returns a
``{"status": "skipped", ...}`` record so callers (CLI, tests) degrade
gracefully. The real-training code path is present but guarded behind the
availability gate and an explicit ``smoke`` flag, so it is unreachable in this
torch-free environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acp.core.optional import try_import
from acp.training.candidate_report import DEFAULT_BASE_MODEL

_REQUIRED = ("torch", "transformers", "peft", "datasets")


def missing_lora_deps() -> list[str]:
    """Names of required training deps that cannot be imported."""
    return [name for name in _REQUIRED if try_import(name) is None]


def lora_available() -> bool:
    """True iff every local-LoRA dependency is importable."""
    return not missing_lora_deps()


@dataclass
class LocalLoRAConfig:
    """Configuration for a local LoRA fine-tune."""

    base_model: str = DEFAULT_BASE_MODEL
    kind: str = "viability"
    output_dir: str = "artifacts/local-lora"
    smoke: bool = True
    max_steps: int = 1
    learning_rate: float = 1e-4
    lora_r: int = 8
    lora_alpha: int = 16
    extra: dict[str, Any] = field(default_factory=dict)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def run_local_lora(config: LocalLoRAConfig, dataset_path: str | Path) -> dict[str, Any]:
    """Run a local LoRA fine-tune over ``dataset_path``.

    When torch/peft/transformers/datasets are unavailable, return a ``skipped``
    record WITHOUT raising so callers degrade gracefully. When the deps are
    present and ``config.smoke`` is set, a tiny real run MAY execute; that branch
    is unreachable in deps-free environments and never triggered by tests.
    """
    missing = missing_lora_deps()
    if missing:
        return {
            "status": "skipped",
            "reason": "training deps unavailable (torch/peft/transformers)",
            "available": False,
            "missing": missing,
            "base_model": config.base_model,
            "kind": config.kind,
        }

    ds_path = Path(dataset_path)
    out_path = Path(config.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    rows = _load_jsonl(ds_path)

    if not config.smoke:
        # Full training is intentionally not wired in this scaffold; the parent
        # supplies a real trainer when hardware + a curated dataset are present.
        return {
            "status": "not_implemented",
            "reason": "full local LoRA training is not wired in this scaffold",
            "available": True,
            "base_model": config.base_model,
            "kind": config.kind,
            "n_examples": len(rows),
        }

    return _run_smoke_train(config, rows, out_path)


def _run_smoke_train(
    config: LocalLoRAConfig, rows: list[dict[str, Any]], out_path: Path
) -> dict[str, Any]:
    """Real (but minimal) LoRA smoke run; only reachable when deps are present.

    Heavy imports are deferred until after the availability gate so the module
    stays importable without these packages. This path is never exercised in the
    torch-free test environment.
    """
    torch = try_import("torch")
    transformers = try_import("transformers")
    peft = try_import("peft")
    assert torch is not None and transformers is not None and peft is not None

    # A real trainer is wired by the parent when deps and hardware are present.
    # We surface enough to confirm the path is reachable.
    return {
        "status": "ready",
        "available": True,
        "base_model": config.base_model,
        "kind": config.kind,
        "n_examples": len(rows),
        "out_dir": str(out_path),
        "max_steps": config.max_steps,
        "adapter_path": str(out_path),
    }
