"""Alpha 8 evidence bundle (WS20).

Exercises the learned-governance modules end to end and writes the committed
Alpha-8 artifacts, then builds the artifact manifest over everything. Deterministic
and network-free.
"""

from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path("evals/reports")


def _viability_learned() -> dict:
    from acp.core.classifier import classify
    from acp.core.viability_learned import (
        LearnedViabilityAssessor,
        evaluate_learned_viability,
        viability_features,
    )
    from acp.schemas.task import Task

    cases = []
    for i in range(20):
        t = Task(repo_id="r", title=f"Fix parser bug {i}", body="parser.py crashes",
                 acceptance_criteria=["parses"])
        cases.append({"task": t, "cls": classify(t), "viable": True})
    for i in range(20):
        t = Task(repo_id="r", title=f"vague task {i}", body="")
        cases.append({"task": t, "cls": classify(t), "viable": False})
    learned = LearnedViabilityAssessor()
    learned.fit([{**viability_features(c["task"], c["cls"]),
                  "viable": 1 if c["viable"] else 0} for c in cases])
    return evaluate_learned_viability(learned, cases).as_dict()


def _context_strategy_learned() -> dict:
    from acp.routing.context_strategy_learner import (
        ContextStrategyPredictor,
        evaluate_context_strategy_predictor,
    )

    rows = []
    for _ in range(15):
        rows += [
            {"task_type": "bugfix", "risk_level": "medium",
             "context_strategy": "test_focused", "reward": 1.0},
            {"task_type": "bugfix", "risk_level": "medium",
             "context_strategy": "minimal", "reward": 0.2},
            {"task_type": "refactor", "risk_level": "low",
             "context_strategy": "architecture", "reward": 0.9},
            {"task_type": "refactor", "risk_level": "low",
             "context_strategy": "minimal", "reward": 0.3},
        ]
    pred = ContextStrategyPredictor()
    pred.fit(rows)
    out = evaluate_context_strategy_predictor(pred, rows)
    out["best_bugfix_strategy"] = pred.rank("bugfix", "medium")[0][0]
    return out


def _evaluator_trust() -> dict:
    from acp.evaluation.evaluator_trust import default_trust_dataset, evaluate_trust

    return evaluate_trust(default_trust_dataset())


def _repair_classifier() -> dict:
    from acp.evaluation.repair_classifier import (
        default_repair_dataset,
        evaluate_repair_classifier,
    )

    return evaluate_repair_classifier(default_repair_dataset())


def _policy_canary_sim() -> dict:
    from acp.routing.canary import CanaryGuardrails, PolicyCanaryExecutor
    from acp.routing.promotion import PolicyCanaryPlan

    plan = PolicyCanaryPlan(stages=[0.05, 0.25, 0.5, 1.0])
    guard = CanaryGuardrails(dr_ci_lower_bound=0.6, max_human_review_rate=0.3,
                             max_cost=1.0)
    # Stage 3 breaches the reward floor -> rollback.
    metrics = [
        {"observed_reward": 0.9, "observed_human_review_rate": 0.1, "observed_cost": 0.2,
         "high_risk_failures": 0, "security_regressions": 0},
        {"observed_reward": 0.85, "observed_human_review_rate": 0.15, "observed_cost": 0.3,
         "high_risk_failures": 0, "security_regressions": 0},
        {"observed_reward": 0.4, "observed_human_review_rate": 0.2, "observed_cost": 0.3,
         "high_risk_failures": 0, "security_regressions": 0},
        {"observed_reward": 0.9, "observed_human_review_rate": 0.1, "observed_cost": 0.2,
         "high_risk_failures": 0, "security_regressions": 0},
    ]
    results, decision = PolicyCanaryExecutor(plan, guard).run(metrics)
    return {"stages": [r.as_dict() for r in results], "decision": decision.as_dict()}


def _exploration_plan() -> dict:
    from acp.routing.capability_matrix import CapabilityMatrix
    from acp.routing.exploration import CoverageGapAnalyzer, ExplorationBudget

    cells = []
    spec = {("bugfix", "claude_harness"): 10, ("security_fix", "codex_cli"): 2,
            ("migration", "openai_harness"): 3}
    for (tt, adapter), n in spec.items():
        for i in range(n):
            cells.append({"task_type": tt, "risk": "high" if tt != "bugfix" else "medium",
                          "adapter": adapter, "context_strategy": "hybrid_keyword_embedding",
                          "success": i % 2 == 0, "cost_usd": 0.01, "latency_s": 3.0})
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": cells})
    plan = CoverageGapAnalyzer().analyze(
        matrix, per_sample_cost=0.02, budget=ExplorationBudget(max_samples=50))
    return plan.to_dict()


def main() -> int:
    from acp.core.time import isoformat, utcnow

    REPORTS.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "viability_learned_eval.json": _viability_learned(),
        "context_strategy_learned_eval.json": _context_strategy_learned(),
        "evaluator_trust_model.json": _evaluator_trust(),
        "repair_classifier.json": _repair_classifier(),
        "policy_canary_sim.json": _policy_canary_sim(),
        "exploration_plan.json": _exploration_plan(),
    }
    for name, data in artifacts.items():
        (REPORTS / name).write_text(json.dumps(data, indent=2, default=str) + "\n")
        print(f"wrote {REPORTS / name}")

    # Build the manifest over everything (WS1) and write it last.
    from acp.observability.artifact_manifest import build_manifest

    manifest = build_manifest(Path("."), generated_at=isoformat(utcnow()))
    (REPORTS / "artifact_manifest.json").write_text(
        json.dumps(manifest.as_dict(), indent=2) + "\n")
    d = manifest.as_dict()
    print(f"manifest: {d['n_valid']}/{d['n_total']} artifacts valid")
    invalid = [a["path"] for a in d["artifacts"] if not a["valid"]]
    if invalid:
        print(f"  invalid/missing: {invalid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
