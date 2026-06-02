"""Artifact truth (WS1) + model promotion gate / memorization audit (WS8)."""

from __future__ import annotations

import json

from acp.observability.artifact_manifest import build_manifest, validate_artifact
from acp.training.model_governance import (
    MemorizationAudit,
    ModelPromotionGate,
)


def test_validate_artifact_missing(tmp_path) -> None:
    e = validate_artifact("evals/reports/x.json", ["a"], tmp_path)
    assert not e.exists and not e.valid
    assert "missing" in e.errors[0]


def test_validate_artifact_malformed_json(tmp_path) -> None:
    p = tmp_path / "evals" / "reports"
    p.mkdir(parents=True)
    (p / "bad.json").write_text("{not json")
    e = validate_artifact("evals/reports/bad.json", ["a"], tmp_path)
    assert e.exists and not e.valid
    assert any("JSON" in err for err in e.errors)


def test_validate_artifact_missing_keys(tmp_path) -> None:
    p = tmp_path / "evals" / "reports"
    p.mkdir(parents=True)
    (p / "r.json").write_text(json.dumps({"a": 1}))
    e = validate_artifact("evals/reports/r.json", ["a", "b"], tmp_path)
    assert e.exists and not e.valid
    assert any("missing required keys" in err for err in e.errors)


def test_valid_artifact_hashed_and_summarized(tmp_path) -> None:
    p = tmp_path / "evals" / "reports"
    p.mkdir(parents=True)
    (p / "r.json").write_text(json.dumps({"a": 1, "n": 42, "accuracy": 0.9}))
    e = validate_artifact("evals/reports/r.json", ["a"], tmp_path)
    assert e.valid and e.hash and e.size_bytes
    assert e.summary.get("n") == 42 and e.summary.get("accuracy") == 0.9


def test_build_manifest_reports_invalid(tmp_path) -> None:
    m = build_manifest(tmp_path, generated_at="2026-06-02",
                       registry={"evals/reports/a.json": ["x"]})
    assert not m.all_valid()
    assert m.invalid()[0].path == "evals/reports/a.json"
    assert "n_valid" in m.as_dict()


def test_memorization_audit_flags_canary() -> None:
    audit = MemorizationAudit(canaries=["sk-CANARY-123", "secret-token-xyz"])
    clean = audit.audit(["here is some normal model output"])
    assert clean["clean"] is True
    leaked = audit.audit(["oops the value was sk-CANARY-123 indeed"])
    assert leaked["clean"] is False
    assert "sk-CANARY-123" in leaked["leaked"]


def test_model_promotion_gate_promotes_good_model() -> None:
    gate = ModelPromotionGate()
    d = gate.evaluate(
        candidate_accuracy=0.9, rules_baseline_accuracy=0.7, prompt_baseline_accuracy=0.75,
        temporal_holdout_passed=True, repo_holdout_passed=True, leakage_clean=True,
        memorization_clean=True, high_risk_degradation=0.0, cost_ratio=1.0,
        latency_ratio=1.0, rollback_plan="revert to rules assessor")
    assert d.promote is True


def test_model_promotion_gate_blocks_on_failures() -> None:
    gate = ModelPromotionGate()
    d = gate.evaluate(
        candidate_accuracy=0.69, rules_baseline_accuracy=0.7, prompt_baseline_accuracy=0.75,
        temporal_holdout_passed=False, repo_holdout_passed=True, leakage_clean=False,
        memorization_clean=False, high_risk_degradation=0.1, cost_ratio=3.0,
        latency_ratio=1.0, rollback_plan=None)
    assert d.promote is False
    names = {r.split(":")[1].split("(")[0].strip() for r in d.reasons}
    assert "beats_rules_baseline" in names
    assert "memorization_audit" in names
    assert "rollback_plan_exists" in names
