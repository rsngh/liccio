"""Unit tests for the local model training scaffold (Alpha 8 WS7).

These tests must pass without torch/peft/transformers and without a GPU.
"""

from __future__ import annotations

from acp.training.local_eval import evaluate_adapter
from acp.training.local_lora import (
    LocalLoRAConfig,
    lora_available,
    run_local_lora,
)
from acp.training.model_card import ModelCard, render_markdown
from acp.training.model_governance import ModelPromotionGate
from acp.training.model_registry import ModelArtifact, ModelRegistry


def test_lora_available_is_bool_and_false_here() -> None:
    result = lora_available()
    assert isinstance(result, bool)
    assert result is False  # torch/peft/transformers not installed


def test_run_local_lora_skips_gracefully(tmp_path) -> None:
    ds = tmp_path / "train.jsonl"
    ds.write_text('{"prompt": "x", "completion": "y"}\n', encoding="utf-8")
    cfg = LocalLoRAConfig(kind="viability", smoke=True)
    out = run_local_lora(cfg, ds)  # must not raise
    assert out["status"] == "skipped"
    assert out["available"] is False
    assert "training deps unavailable" in out["reason"]


def test_model_registry_roundtrip(tmp_path) -> None:
    reg = ModelRegistry(index_path=tmp_path / "index.json")
    art = ModelArtifact(
        id="run-1", base_model="Qwen2.5-Coder-1.5B-Instruct",
        dataset_kind="viability", adapter_path="/tmp/adapter",
        metrics={"acc": 0.9},
    )
    reg.register(art)
    assert reg.get("run-1") is art
    assert [a.id for a in reg.list()] == ["run-1"]

    # On-disk index reloads.
    reg2 = ModelRegistry(index_path=tmp_path / "index.json")
    loaded = reg2.get("run-1")
    assert loaded is not None
    assert loaded.base_model == "Qwen2.5-Coder-1.5B-Instruct"
    assert loaded.metrics == {"acc": 0.9}


def test_model_card_renders_markdown() -> None:
    card = ModelCard(
        base_model="Qwen2.5-Coder-1.5B-Instruct",
        dataset_kind="viability",
        n_train=80, n_test=20,
        intended_use="predict task viability",
        limitations=["small sample", "stub-evaluated"],
    )
    md = render_markdown(card)
    assert "Qwen2.5-Coder-1.5B-Instruct" in md
    assert "Limitations" in md
    assert "small sample" in md


def test_evaluate_adapter_shapes_for_gate() -> None:
    art = ModelArtifact(
        id="run-2", base_model="Qwen2.5-Coder-1.5B-Instruct",
        dataset_kind="viability",
    )
    cases = [
        {"inputs": {}, "target": {"viable": True}},
        {"inputs": {}, "target": {"viable": True}},
        {"inputs": {}, "target": {"viable": False}},
    ]
    metrics = evaluate_adapter(art, cases)
    assert metrics["predictor"] == "stub"
    assert metrics["adapter_loaded"] is False
    # All ModelPromotionGate.evaluate kwargs are present and consumable.
    decision = ModelPromotionGate().evaluate(
        candidate_accuracy=metrics["candidate_accuracy"],
        rules_baseline_accuracy=metrics["rules_baseline_accuracy"],
        prompt_baseline_accuracy=metrics["prompt_baseline_accuracy"],
        temporal_holdout_passed=metrics["temporal_holdout_passed"],
        repo_holdout_passed=metrics["repo_holdout_passed"],
        leakage_clean=metrics["leakage_clean"],
        memorization_clean=metrics["memorization_clean"],
        high_risk_degradation=metrics["high_risk_degradation"],
        cost_ratio=metrics["cost_ratio"],
        latency_ratio=metrics["latency_ratio"],
        rollback_plan=metrics["rollback_plan"],
    )
    # Stub mirrors the baseline, so it must NOT be promoted.
    assert decision.promote is False
