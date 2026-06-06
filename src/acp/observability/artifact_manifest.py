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
    "evals/reports/vendor_harness_live.json": ["experiment", "available", "passed",
                                               "live_proven", "harnesses"],
    "evals/reports/local_lora_pilot.json": ["available", "status"],
    # Alpha 11 WS14 — REAL observed live bakeoff
    "evals/reports/live_bakeoff_capability_matrix.json": ["n_cells"],
    "evals/reports/live_bakeoff_ope.json": ["source", "n"],
    # Alpha 12 WS6/WS9
    "evals/reports/harness_metrics.json": ["har", "hfr", "pwl"],
    "evals/reports/trajectory_judge.json": ["comparison"],
    # Round 12 — measurement-trust layer (WS1/WS3/WS4)
    "evals/reports/measurement_hygiene.json": ["n_attempts", "solve_rate", "by_outcome"],
    "evals/reports/harness_availability_audit.json": ["expected", "degraded"],
    "evals/reports/tool_activation_metrics.json": ["by_adapter", "n_attempts"],
    # Round 13 — measurement-quality score + trust verdict (WS3/WS10)
    "evals/reports/measurement_quality.json": ["score", "trusted"],
    # Round 15 — live SkillOpt optimization run
    "reports/live/skillopt_run.json": ["experiment", "base_score", "best_score"],
    # Round 16 — cross-harness skill transfer
    "reports/live/skill_transfer.json": ["experiment", "baseline_score", "transfer_gain"],
    # Round 17 — online A/B skill canary
    "reports/live/skill_canary.json": ["experiment", "control_rate", "canary_rate", "promote"],
    # Alpha 22 WS16 — vendor + SkillOpt live canary
    "reports/live/vendor_skill_canary.json": ["experiment", "harness", "decision"],
    # Alpha 22 WS18 — cross-harness vendor transfer
    "reports/live/cross_harness_vendor_transfer.json": [
        "experiment", "scope_recommendation", "verdicts"],
    # Alpha 23 WS4 — graded benchmark baseline (capability by difficulty)
    "reports/live/benchmark_baseline.json": [
        "experiment", "harness", "overall_solve_rate", "by_difficulty"],
    # Alpha 23 WS5 — benchmark skill A/B (lift by difficulty)
    "reports/live/benchmark_skill_ab.json": [
        "experiment", "harness", "overall", "by_difficulty", "decision"],
    # Alpha 23 WS8 — timeout-confound (apparent gap that closes when budget relaxed)
    "reports/live/timeout_confound.json": [
        "experiment", "harness", "low", "high", "verdict"],
    # Alpha 23 WS10 — underspecified-task skill A/B (skill discipline, not timeout)
    "reports/live/underspecified_skill_ab.json": [
        "experiment", "harness", "baseline_rate", "skill_rate", "decision"],
    # Alpha 23 WS11 — proven skill promoted via staged canary (loop closed live)
    "reports/live/underspecified_promotion.json": [
        "experiment", "promoted", "deployed", "active_skill", "stages"],
    # Alpha 24 area 2 — weak-model best-of-k bakeoff + cost curve
    "evals/reports/weak_model_candidate_bakeoff.json": ["experiment", "model", "by_cohort"],
    "evals/reports/best_of_k_cost_curve.json": ["experiment", "model", "rows"],
    # Alpha 24 area 1 — advisor escalation
    "evals/reports/advisor_policy.json": ["experiment", "executor", "advisor"],
    "evals/reports/advisor_bakeoff.json": ["experiment", "executor_only", "executor_plus_advisor"],
    "evals/reports/advisor_cost_quality_frontier.json": ["experiment", "points"],
    # Alpha 24 area 3 — topology controller search
    "evals/reports/topology_controller_search.json": ["experiment", "baseline", "best", "improved"],
    "evals/reports/topology_ope.json": ["experiment", "candidates"],
    "evals/reports/topology_policy_canary.json": ["experiment", "requires_canary_before_promotion"],
    # Alpha 24 area 6 — context strategy (grep vs embedding vs hybrid)
    "evals/reports/grep_vs_embedding_bakeoff.json": ["experiment", "by_strategy"],
    "evals/reports/context_strategy_ope.json": ["experiment", "chosen", "scores"],
    "evals/reports/context_reuse_frontier.json": ["experiment", "embedding_amortization"],
    # Alpha 24 area 7 — memory lifecycle / aging
    "evals/reports/memory_aging_benchmark.json": ["experiment", "curves", "revision_repairs"],
    "evals/reports/memory_lifecycle.json": ["experiment", "transitions", "private_memory_isolated"],
    "evals/reports/memory_poisoning.json": ["experiment", "n_blocked", "all_blocked"],
    # Alpha 24 area 11 — HeavySkill parallel deliberation
    "evals/reports/heavyskill_bugfix.json": ["experiment", "model", "rows"],
    "evals/reports/parallel_deliberation_skill.json": ["experiment", "mean_verify_savings"],
    # Alpha 24 area 12 — tool-format RL dataset
    "evals/reports/tool_format_dataset.json": ["experiment", "n_examples", "malformed_rate"],
    "evals/reports/harness_activation_training.json": ["experiment", "by_adapter"],
    # Alpha 24 area 10 — workflow distillation
    "evals/reports/workflow_distillation_dataset.json": ["experiment", "n_train", "leakage_clean"],
    "evals/reports/small_model_training_smoke.json": ["experiment", "trained"],
    "evals/reports/memorization_audit.json": [
        "experiment", "memorization_overlap", "leakage_clean"],
    # Alpha 24 area 4 — meta-harness optimization
    "evals/reports/meta_harness_patch.json": ["experiment", "best_patch", "n_accepted"],
    "evals/reports/harness_regression_suite.json": ["experiment", "negative_transfer_bounded"],
    "evals/reports/harness_canary.json": ["experiment", "requires_canary_before_deploy"],
    # Alpha 24 area 13 — DGM variant archive
    "evals/reports/agent_variant_archive.json": ["experiment", "n_archived", "all_archived_safe"],
    "evals/reports/open_ended_harness_evolution.json": [
        "experiment", "improved", "rejected_unsafe"],
    # Alpha 24 area 14 — confidence pruning
    "evals/reports/confidence_pruning.json": ["experiment", "kept", "estimated_verify_savings"],
    "evals/reports/advisor_confidence_trigger.json": [
        "experiment", "low_confidence_triggers_advisor"],
    # Alpha 24 area 15 — research-engineering benchmark
    "evals/reports/research_engineering_benchmark.json": ["experiment", "mean_recovered", "rows"],
    "evals/reports/nanogpt_style_agent_eval.json": [
        "experiment", "mean_recovered", "tuning_penalized"],
    "evals/reports/algorithmic_progress_report.json": [
        "experiment", "rewards_algorithmic_over_tuning"],
    # Alpha 25 test F — best-of-k on genuinely hard tasks
    "evals/reports/hard_best_of_k.json": [
        "experiment", "single_shot_rate", "best_of_k_rate", "ceiling_escaped"],
    # Alpha 29 — compute-escalation policy bakeoff
    "evals/reports/compute_policy_bakeoff.json": ["experiment", "arms", "per_task"],
    # Alpha 26 — vendor-native corpus capability matrix
    "evals/reports/vendor_capability_matrix.json": [
        "experiment", "harness", "baseline", "with_skill"],
    # Item 4 — sample adequacy (statistical robustness of observed cells)
    "evals/reports/sample_adequacy.json": ["experiment", "by_tier", "robust_fraction"],
    # Round 25 — evidence tier + activation-aware solve-rate denominators
    "evals/reports/evidence_quality.json": [
        "experiment", "evidence_tier", "solve_rate_activated", "solve_rate_conclusive"],
    # Alpha 26 — production shadow mode (recommend-only, no autonomous write)
    "evals/reports/production_shadow.json": [
        "experiment", "no_autonomous_writes", "every_recommendation_has_dossier"],
    # Round 25 test C / Alpha 29 — compute escalation benchmark
    "evals/reports/compute_escalation_benchmark.json": [
        "experiment", "decision_table", "policy_validated"],
    # Alpha 29 — repo-replay realistic bug tasks (live)
    "evals/reports/repo_replay_live.json": [
        "experiment", "evidence_tier", "single_shot_rate", "best_of_k_rate"],
    # Round 19 — end-to-end live autonomous self-improvement cycle
    "reports/live/autonomous_cycle.json": ["experiment", "cycle", "dashboard"],
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
