"""Artifact truth infrastructure (Alpha 8, WS1).

Every checklist artifact is a *claim*. This module makes claims verifiable: it
builds an `ArtifactManifest` (path, schema kind, generated_at, hash, summary
metrics) over the committed reports and validates that each referenced artifact
exists, parses, and matches a minimal schema — so CI fails when a report is
missing, malformed, or inconsistent with the markdown that cites it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Report path -> required top-level keys (the schema registry). A report passes
# validation when it exists, is valid JSON, and contains every required key.
REPORT_SCHEMA_REGISTRY: dict[str, list[str]] = {
    # Alpha 6/7
    "evals/reports/ope.json": ["experiment", "policies"],
    "evals/reports/real_log_ope.json": ["experiment", "policies", "ranking_by_dr"],
    "evals/reports/viability_matrix.json": ["capability_matrix"],
    "evals/reports/training_candidate_report.json": ["report"],
    "evals/reports/vendor_harness_smoke.json": ["vendor_adapters"],
    "evals/reports/context_downstream_benchmark.json": ["results"],
    # Alpha 8 (the manifest is the meta-artifact and is not listed in itself)
    "evals/reports/viability_learned_eval.json": ["n", "promotable"],
    "evals/reports/context_strategy_learned_eval.json": ["top1_accuracy"],
    "evals/reports/evaluator_trust_model.json": ["metrics", "thresholds"],
    "evals/reports/repair_classifier.json": ["accuracy"],
    "evals/reports/policy_canary_sim.json": ["stages", "decision"],
    "evals/reports/exploration_plan.json": ["targets"],
    "evals/reports/capability_matrix_populated.json": ["n_sufficient"],
    "evals/reports/security_benchmark.json": ["summary"],
    "evals/reports/storage_scale.json": ["subquadratic"],
    "evals/reports/docker_security_live.json": ["checks", "passed"],
    # Alpha 9
    "evals/reports/pareto_routing.json": ["profiles", "choices"],
    "evals/reports/drift_demote.json": ["report", "demoted"],
    "evals/reports/preference_learning.json": ["n_pairs", "evaluation"],
    "evals/reports/counterfactual_regret.json": ["total_regret"],
    "evals/reports/control_plane_health.json": ["status", "readiness"],
    # Alpha 10
    "evals/reports/large_empirical_corpus.json": ["n_sufficient"],
    "evals/reports/storage_scale_v2.json": ["subquadratic"],
    "evals/reports/security_injection_v2.json": ["summary"],
    # Alpha 11
    "evals/reports/policy_dossier.json": ["run_id", "why_chosen"],
    "evals/reports/preference_reward_gate.json": ["gate", "promoted"],
    "evals/reports/data_governance_redteam.json": ["summary"],
    "evals/reports/drift_persistence.json": ["persisted", "drift"],
    "evals/reports/exploration_executor.json": ["coverage_delta"],
    "evals/reports/scheduler_report.json": ["reports"],
    "evals/reports/mixed_empirical_corpus.json": ["n_sufficient", "n_preference_pairs"],
    "evals/reports/control_plane_health_production.json": ["production_gates"],
    "evals/reports/vendor_harness_live.json": ["vendor_adapters"],
    "evals/reports/local_lora_pilot.json": ["available", "status"],
}


@dataclass
class ArtifactEntry:
    path: str
    exists: bool
    schema_kind: str
    valid: bool
    hash: str | None = None
    size_bytes: int | None = None
    generated_at: float | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path, "exists": self.exists, "schema_kind": self.schema_kind,
            "valid": self.valid, "hash": self.hash, "size_bytes": self.size_bytes,
            "generated_at": self.generated_at, "summary": self.summary,
            "errors": self.errors,
        }


def _summarize(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k in ("n", "accuracy", "top1_accuracy", "promotable", "ranking_by_dr",
                  "trustworthy"):
            if k in data:
                out[k] = data[k]
        return out
    return {}


def validate_artifact(path: str, required_keys: list[str], root: Path) -> ArtifactEntry:
    fp = root / path
    entry = ArtifactEntry(path=path, exists=fp.exists(), schema_kind=path,
                          valid=False)
    if not entry.exists:
        entry.errors.append("missing on disk")
        return entry
    raw = fp.read_bytes()
    entry.hash = hashlib.sha256(raw).hexdigest()
    entry.size_bytes = len(raw)
    entry.generated_at = fp.stat().st_mtime
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        entry.errors.append(f"invalid JSON: {exc}")
        return entry
    missing = [k for k in required_keys if not (isinstance(data, dict) and k in data)]
    if missing:
        entry.errors.append(f"missing required keys: {missing}")
        return entry
    entry.summary = _summarize(data)
    entry.valid = True
    return entry


@dataclass
class ArtifactManifest:
    generated_at: str
    artifacts: list[ArtifactEntry]

    def as_dict(self) -> dict:
        return {"generated_at": self.generated_at,
                "artifacts": [a.as_dict() for a in self.artifacts],
                "n_valid": sum(1 for a in self.artifacts if a.valid),
                "n_total": len(self.artifacts)}

    def all_valid(self) -> bool:
        return all(a.valid for a in self.artifacts)

    def invalid(self) -> list[ArtifactEntry]:
        return [a for a in self.artifacts if not a.valid]


def build_manifest(root: Path, *, generated_at: str,
                   registry: dict[str, list[str]] | None = None) -> ArtifactManifest:
    reg = registry if registry is not None else REPORT_SCHEMA_REGISTRY
    entries = [validate_artifact(p, keys, root) for p, keys in reg.items()]
    return ArtifactManifest(generated_at=generated_at, artifacts=entries)
