"""Model card schema + markdown renderer (Alpha 8 WS7).

A :class:`ModelCard` captures the provenance, intended use, limitations, and
governance summaries (eval, leakage, memorization) for a locally fine-tuned
adapter. :func:`render_markdown` turns a card into a human-readable report that
can be shipped alongside the adapter artifact. No heavy deps: importable without
torch/peft/transformers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from acp.core.time import isoformat, utcnow


@dataclass
class ModelCard:
    """Documentation for a fine-tuned model/adapter artifact."""

    base_model: str
    dataset_kind: str
    n_train: int = 0
    n_test: int = 0
    intended_use: str = ""
    limitations: list[str] = field(default_factory=list)
    training_data_provenance: dict[str, Any] = field(default_factory=dict)
    eval_summary: dict[str, Any] = field(default_factory=dict)
    leakage_audit: dict[str, Any] = field(default_factory=dict)
    memorization_audit: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serializable representation of the card."""
        return {
            "base_model": self.base_model,
            "dataset_kind": self.dataset_kind,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "intended_use": self.intended_use,
            "limitations": list(self.limitations),
            "training_data_provenance": dict(self.training_data_provenance),
            "eval_summary": dict(self.eval_summary),
            "leakage_audit": dict(self.leakage_audit),
            "memorization_audit": dict(self.memorization_audit),
            "created_at": isoformat(self.created_at),
        }


def _render_kv(title: str, data: dict[str, Any]) -> list[str]:
    lines = [f"## {title}", ""]
    if not data:
        lines.append("_none recorded_")
        lines.append("")
        return lines
    for key, value in data.items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    return lines


def render_markdown(card: ModelCard) -> str:
    """Render ``card`` as a markdown document."""
    lines: list[str] = [
        f"# Model Card: {card.base_model} ({card.dataset_kind})",
        "",
        f"- **Base model**: {card.base_model}",
        f"- **Dataset kind**: {card.dataset_kind}",
        f"- **Train examples**: {card.n_train}",
        f"- **Test examples**: {card.n_test}",
        f"- **Created at**: {isoformat(card.created_at)}",
        "",
        "## Intended Use",
        "",
        card.intended_use or "_not specified_",
        "",
        "## Limitations",
        "",
    ]
    if card.limitations:
        lines.extend(f"- {item}" for item in card.limitations)
    else:
        lines.append("_none recorded_")
    lines.append("")
    lines.extend(_render_kv("Training Data Provenance", card.training_data_provenance))
    lines.extend(_render_kv("Evaluation Summary", card.eval_summary))
    lines.extend(_render_kv("Leakage Audit", card.leakage_audit))
    lines.extend(_render_kv("Memorization Audit", card.memorization_audit))
    return "\n".join(lines)
