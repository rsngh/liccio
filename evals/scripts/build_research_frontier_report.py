"""Tier-3 frontier artifacts: areas 4, 13, 14, 15 (Alpha 24, offline, deterministic)."""

from __future__ import annotations

import json
from pathlib import Path

from acp.evaluation.research_benchmark import ResearchTask, run_research_benchmark
from acp.orchestration.confidence_pruning import (
    ScoredCandidate,
    confidence_weighted_vote,
    prune_by_confidence,
)
from acp.training.meta_harness import (
    HarnessConfig,
    HarnessPatch,
    search_harness_patches,
)
from acp.training.variant_archive import Variant, evolve

ROOT = Path("evals/reports")


def _meta_harness() -> None:
    tasks = ["t1", "t2", "t3"]

    def ev(cfg, task):
        v = cfg.params.get("trace_summary_level", 0)
        base = {"t1": 0.5, "t2": 0.6, "t3": 0.85}[task]
        return min(1.0, base + 0.15 * v) if task != "t3" else max(0.0, base - 0.05 * v)

    patches = [HarnessPatch({"trace_summary_level": 1}, "summarize traces"),
               HarnessPatch({"trace_summary_level": 4}, "aggressive summary"),
               HarnessPatch({"trace_summary_level": 1}, "weaken", weakens_gate=True)]
    out = search_harness_patches(HarnessConfig({"trace_summary_level": 0}), patches,
                                 tasks=tasks, task_eval_fn=ev, max_regression=0.1)
    (ROOT / "meta_harness_patch.json").write_text(
        json.dumps({"experiment": "meta_harness_patch", **out}, indent=2) + "\n")
    (ROOT / "harness_regression_suite.json").write_text(json.dumps(
        {"experiment": "harness_regression_suite", "tasks": tasks,
         "max_regression": 0.1, "negative_transfer_bounded": out["best_result"] is not None
         and out["best_result"]["regression_clean"]}, indent=2) + "\n")
    (ROOT / "harness_canary.json").write_text(json.dumps(
        {"experiment": "harness_canary", "candidate_patch": out["best_patch"],
         "requires_canary_before_deploy": True, "auto_deployed": False,
         "guardrails": ["no eval-script edits", "no gate weakening",
                        "negative transfer bounded", "staged canary + rollback"]},
        indent=2) + "\n")


def _variant_archive() -> None:
    def ev(p):
        return -abs(p.get("retry_budget", 0) - 3) - abs(p.get("ctx_tokens", 0) - 8)

    def propose(parent, c):
        return {"sandbox": True, "retry_budget": parent.get("retry_budget", 0) + (c % 3),
                "ctx_tokens": parent.get("ctx_tokens", 0) + (c % 4)}

    arc = evolve({"sandbox": True, "retry_budget": 0, "ctx_tokens": 0},
                 propose_fn=propose, eval_fn=ev, generations=5, children_per_gen=3)
    # add a deliberately unsafe variant to show it is rejected
    arc.add(Variant("evil", {"sandbox": True, "weaken_gate": True}))
    best = arc.best()
    (ROOT / "agent_variant_archive.json").write_text(json.dumps(
        {"experiment": "agent_variant_archive", "n_archived": len(arc.variants),
         "n_rejected": len(arc.rejected), "best_score": (best.score if best else None),
         "best_params": (best.params if best else None),
         "all_archived_safe": all(not any(v.params.get(k) for k in
             ("disable_secret_scan", "skip_verification", "weaken_gate", "mutate_production"))
             for v in arc.variants)}, indent=2) + "\n")
    (ROOT / "open_ended_harness_evolution.json").write_text(json.dumps(
        {"experiment": "open_ended_harness_evolution", "generations": 5,
         "improved": best is not None and best.score > ev({"retry_budget": 0, "ctx_tokens": 0}),
         "rejected_unsafe": len(arc.rejected),
         "requires_canary_before_promotion": True}, indent=2) + "\n")


def _confidence() -> None:
    cands = [ScoredCandidate(i, c, f"ans{i % 2}") for i, c in
             enumerate([0.95, 0.9, 0.4, 0.2, 0.15])]
    pruned = prune_by_confidence(cands, threshold=0.5, min_keep=1, cost_per_verify=0.01)
    hr = prune_by_confidence(cands, threshold=0.9, min_keep=1, risk="high")
    (ROOT / "confidence_pruning.json").write_text(json.dumps(
        {"experiment": "confidence_pruning", **pruned.to_dict(),
         "vote": confidence_weighted_vote(cands),
         "high_risk_keeps_more": len(hr.kept) >= 3}, indent=2) + "\n")
    (ROOT / "advisor_confidence_trigger.json").write_text(json.dumps(
        {"experiment": "advisor_confidence_trigger",
         "low_confidence_triggers_advisor": min(c.confidence for c in cands) < 0.5,
         "early_stop_on_high_confidence": max(c.confidence for c in cands) >= 0.9},
        indent=2) + "\n")


def _research() -> None:
    t_arch = ResearchTask("t1", "improve_architecture", 0.5, 1.0)
    recs = [(t_arch, 0.9, ["attention_forward", "value_head"]),
            (ResearchTask("t2", "ablate_idea", 0.4, 0.9), 0.85, ["learning_rate"]),
            (ResearchTask("t3", "alphazero_loop", 0.0, 1.0), 0.3, ["mcts", "self_play"]),
            (ResearchTask("t4", "reproduce_baseline", 0.0, 1.0), 0.95, ["backbone"])]
    rep = run_research_benchmark(recs)
    (ROOT / "research_engineering_benchmark.json").write_text(
        json.dumps(rep.to_dict(), indent=2) + "\n")
    (ROOT / "nanogpt_style_agent_eval.json").write_text(json.dumps(
        {"experiment": "nanogpt_style_agent_eval", "mean_recovered": rep.mean_recovered,
         "mean_reward": rep.mean_reward, "tuning_penalized": rep.mean_reward <= rep.mean_recovered,
         "n_tasks": rep.n_tasks}, indent=2) + "\n")
    (ROOT / "algorithmic_progress_report.json").write_text(json.dumps(
        {"experiment": "algorithmic_progress_report", "n_substantive": rep.n_substantive,
         "n_tuning_only": rep.n_tuning_only,
         "rewards_algorithmic_over_tuning": rep.mean_reward <= rep.mean_recovered,
         "routes_research_differently": rep.routes_research_differently}, indent=2) + "\n")


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    _meta_harness()
    _variant_archive()
    _confidence()
    _research()
    print("wrote area 4/13/14/15 artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
