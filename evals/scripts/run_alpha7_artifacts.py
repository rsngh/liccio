"""Alpha 7 release artifacts (WS19).

Generates the deterministic, network-free Alpha-7 evidence artifacts:

* ``evals/reports/real_log_ope.json`` — multi-policy offline evaluation + the
  promotion-gate decision on a logged-style dataset.
* ``evals/reports/viability_matrix.json`` — a capability matrix built from a
  bakeoff-style report, with low-sample cells flagged (no overclaim).
* ``evals/reports/training_candidate_report.json`` — fine-tuning candidate report
  over a synthetic exhaust bundle.
* ``evals/reports/vendor_harness_smoke.json`` — vendor-harness capability + a
  graceful-unavailability smoke for the registered vendor shims.

Each is committed so a reviewer can answer the Alpha-7 acceptance questions
without rerunning anything.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

REPORTS = Path("evals/reports")


# --------------------------------------------------------------------------
def _real_log_ope() -> dict:
    from acp.routing.ope import OPESample, evaluate_policy, fit_reward_model
    from acp.routing.promotion import evaluate_promotion
    from acp.routing.supervised import SupervisedRoutingPolicy

    world = {
        "bugfix|medium": {"good": "claude_harness", "bad": "fake"},
        "refactor|low": {"good": "openai_harness", "bad": "patch"},
        "security|high": {"good": "claude_harness", "bad": "openai_harness"},
    }

    def key(agent: str) -> str:
        return f"harness|{agent}|-|hybrid_keyword_embedding|standard"

    samples: list[OPESample] = []
    for ctx, arms in world.items():
        cands = [key(arms["good"]), key(arms["bad"])]
        for i in range(80):
            agent = arms["good"] if i % 2 == 0 else arms["bad"]
            samples.append(OPESample(ctx, key(agent), 0.5,
                                     1.0 if agent == arms["good"] else 0.0, cands))
    baseline = sum(s.reward for s in samples) / len(samples)

    def random_t(ctx, action, cands):
        return 1.0 / len(cands)

    q = fit_reward_model(samples)

    def greedy(ctx, action, cands):
        best = max(q(ctx, a) for a in cands)
        winners = [a for a in cands if q(ctx, a) == best]
        return 1.0 / len(winners) if action in winners else 0.0

    sup = SupervisedRoutingPolicy()
    sup.fit([{"context_key": s.context_key, "action_key": s.action_key,
              "reward": s.reward} for s in samples])
    # A temperature-smoothed variant keeps exploratory mass on every arm, so it
    # has full propensity overlap with the logged policy and can pass the gate —
    # the fully-greedy target below is *correctly* blocked for poor overlap.
    sup_explore = SupervisedRoutingPolicy(temperature=0.25)
    sup_explore.fit([{"context_key": s.context_key, "action_key": s.action_key,
                      "reward": s.reward} for s in samples])

    policies = {
        "random": evaluate_policy(samples, random_t, seed=1),
        "greedy": evaluate_policy(samples, greedy, seed=1),
        "supervised": evaluate_policy(samples, sup.as_target(), seed=1),
        "supervised_explore": evaluate_policy(samples, sup_explore.as_target(), seed=1),
    }
    gate_greedy = evaluate_promotion(policies["supervised"], baseline_value=baseline)
    gate_explore = evaluate_promotion(policies["supervised_explore"], baseline_value=baseline)
    return {
        "experiment": "alpha7_real_log_ope",
        "note": "synthetic logged dataset; same machinery runs on real logs via "
                "AppService.real_log_ope_report",
        "n": len(samples),
        "logged_mean_reward": round(baseline, 6),
        "policies": {k: v.as_dict() for k, v in policies.items()},
        "ranking_by_dr": sorted(policies, key=lambda k: policies[k].dr.value,
                                reverse=True),
        "promotion_gate_greedy_supervised": gate_greedy.as_dict(),
        "promotion_gate_explore_supervised": gate_explore.as_dict(),
    }


# --------------------------------------------------------------------------
def _viability_matrix() -> dict:
    from acp.core.classifier import classify
    from acp.core.viability import assess_viability
    from acp.routing.capability_matrix import CapabilityMatrix
    from acp.schemas.task import Task

    # A bakeoff-style report: two task types × two adapters × repeated runs.
    cells = []
    spec = {
        ("bugfix", "claude_harness"): (1.0, 0.01),
        ("bugfix", "fake"): (0.2, 0.0),
        ("security_fix", "claude_harness"): (0.9, 0.02),
        ("security_fix", "openai_harness"): (0.7, 0.015),
    }
    for (tt, adapter), (succ, cost) in spec.items():
        for i in range(8):
            cells.append({
                "task_type": tt, "risk": "high" if tt == "security_fix" else "medium",
                "adapter": adapter, "is_harness": adapter.endswith("harness"),
                "context_strategy": "hybrid_keyword_embedding",
                "success": (i / 8.0) < succ, "cost_usd": cost, "latency_s": 3.0,
            })
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": cells})

    task = Task(repo_id="r", title="Fix SQL injection in auth login",
                body="An attacker can inject SQL in the login path.",
                acceptance_criteria=["injection blocked"])
    viability = assess_viability(task, classify(task))
    return {
        "experiment": "alpha7_viability_matrix",
        "capability_matrix": matrix.to_dict(),
        "sample_viability_assessment": viability.model_dump(mode="json"),
    }


# --------------------------------------------------------------------------
def _training_candidate() -> dict:
    from acp.schemas.training import TrainingExample
    from acp.training.candidate_report import build_candidate_report

    # Synthetic exhaust -> a handful of examples across kinds.
    by_kind: dict[str, list[TrainingExample]] = {}
    for kind, n in (("routing", 12), ("human_review", 8), ("evaluator", 10), ("repair", 6)):
        by_kind[kind] = [
            TrainingExample(dataset_kind=kind, task_id=f"task_{kind}_{i}",
                            inputs={"feature": i}, target=str(i % 2),
                            label_source="objective")
            for i in range(n)
        ]
    return {"experiment": "alpha7_training_candidate",
            "report": build_candidate_report(by_kind)}


# --------------------------------------------------------------------------
def _vendor_smoke() -> dict:
    import dataclasses

    from acp.agents import build_default_registry
    from acp.agents.capabilities import build_capability_registry

    reg = build_default_registry()
    caps = asyncio.run(build_capability_registry(reg))
    rows = [dataclasses.asdict(e) for e in caps.entries]
    vendor = [r for r in rows if r.get("category") == "vendor"]
    return {
        "experiment": "alpha7_vendor_harness_smoke",
        "note": "vendor shims are registered and capability-gated; availability "
                "reflects this environment",
        "vendor_adapters": vendor,
        "all_adapters": rows,
    }


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "real_log_ope.json": _real_log_ope(),
        "viability_matrix.json": _viability_matrix(),
        "training_candidate_report.json": _training_candidate(),
        "vendor_harness_smoke.json": _vendor_smoke(),
    }
    for name, data in artifacts.items():
        (REPORTS / name).write_text(json.dumps(data, indent=2, default=str) + "\n")
        print(f"wrote {REPORTS / name}")
    ope = artifacts["real_log_ope.json"]
    print(f"OPE ranking={ope['ranking_by_dr']} "
          f"greedy_promote={ope['promotion_gate_greedy_supervised']['promote']} "
          f"explore_promote={ope['promotion_gate_explore_supervised']['promote']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
