"""Fine-tuning candidate report (Alpha-7 WS18).

Given distilled examples grouped by kind, summarize whether the corpus is large
and clean enough to justify a fine-tune: counts per kind, label-source quality,
train/test split sizes, a secret-audit verdict, a majority-class baseline, a
recommended base model, and a ``recommend_finetune`` boolean that is only true
when the sample size clears a threshold AND the leakage audit is clean.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from acp.schemas.training import TrainingExample
from acp.training.dataset_factory import DatasetFactory, ExhaustBundle

DEFAULT_BASE_MODEL = "Qwen2.5-Coder-1.5B-Instruct"
MIN_EXAMPLES_TO_RECOMMEND = 50


def _majority_class_accuracy(examples: list[TrainingExample]) -> float:
    """Accuracy of always predicting the most common target (baseline)."""
    if not examples:
        return 0.0
    labels: Counter[str] = Counter()
    for ex in examples:
        if isinstance(ex.target, dict):
            key = ex.target.get("verdict") or ex.target.get("action_key")
        else:
            key = ex.target
        labels[str(key)] += 1
    return max(labels.values()) / sum(labels.values())


def _label_quality(examples: list[TrainingExample]) -> dict[str, int]:
    sources: Counter[str] = Counter(ex.label_source for ex in examples)
    return dict(sources)


def build_candidate_report(
    examples_by_kind: dict[str, list[TrainingExample]],
    *,
    base_model: str = DEFAULT_BASE_MODEL,
    min_examples: int = MIN_EXAMPLES_TO_RECOMMEND,
) -> dict[str, Any]:
    """Build a fine-tuning candidate report from examples grouped by kind."""
    factory = DatasetFactory()
    empty_bundle = ExhaustBundle()

    per_kind: dict[str, dict[str, Any]] = {}
    all_examples: list[TrainingExample] = []
    secret_survivors = 0
    for kind, examples in examples_by_kind.items():
        all_examples.extend(examples)
        splits: Counter[str] = Counter(ex.split for ex in examples)
        audit = factory._audit(examples, empty_bundle, _noop_config(kind))
        secret_survivors += audit.secret_survivors
        per_kind[kind] = {
            "n_examples": len(examples),
            "label_quality": _label_quality(examples),
            "splits": dict(splits),
            "train": splits.get("train", 0),
            "test": splits.get("test", 0),
            "baseline_majority_accuracy": round(_majority_class_accuracy(examples), 4),
            "leakage_clean": audit.clean,
        }

    total = len(all_examples)
    audit_clean = secret_survivors == 0
    recommend = total >= min_examples and audit_clean

    return {
        "total_examples": total,
        "available_by_kind": {k: v["n_examples"] for k, v in per_kind.items()},
        "per_kind": per_kind,
        "label_quality": _label_quality(all_examples),
        "secret_audit": {"survivors": secret_survivors, "clean": audit_clean},
        "baseline_majority_accuracy": round(_majority_class_accuracy(all_examples), 4),
        "recommended_base_model": base_model,
        "min_examples_threshold": min_examples,
        "recommend_finetune": recommend,
    }


def _noop_config(kind: str) -> Any:
    from acp.schemas.training import DatasetBuildConfig

    return DatasetBuildConfig(kind=kind)
