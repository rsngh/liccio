"""Build Alpha 43 derived artifacts from the scaled arena (GOALS Alpha 43 P0/P5/P7).

Deterministic: reads reports/metarouter_arena_scaled.json and emits
metarouter_policy_compare_scaled.json, context_strategy_ope_v2.json (per context_need, with CIs),
and finops_marginal_value.json. No API calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.metarouter_arena.statistics import wilson_ci  # noqa: E402

from acp.context.context_strategy_ope import ContextStrategyOPE  # noqa: E402
from acp.finops.marginal_value_controller import MarginalValueController  # noqa: E402

_POLICY_TO_STRATEGY = {"cheap_single": "minimal", "grep_router": "grep",
                       "repo_map_router": "repo_map", "abstain_router": "repo_map_plus_abstain"}


def main() -> int:
    arena = json.loads((ROOT / "reports" / "metarouter_arena_scaled.json").read_text())
    from evals.metarouter_arena.task_loader import load_scaled_tasks
    from evals.metarouter_arena.task_pack import TASK_PACK
    need_by_task = {t.name: t.context_need for t in (load_scaled_tasks() + list(TASK_PACK))}

    # 1. policy compare (scaled), ranked by verified success per dollar
    scores = arena["policy_scores"]
    ranked = sorted(scores, key=lambda s: (
        s["verified_success_rate"] / (s["cost_per_verified_success"] or 1e9)), reverse=True)
    (ROOT / "reports" / "metarouter_policy_compare_scaled.json").write_text(json.dumps(
        {"experiment": "metarouter_policy_compare_scaled",
         "ranking": [s["policy"] for s in ranked], "scores": scores,
         "confidence_intervals": arena["confidence_intervals"]}, indent=2) + "\n")

    # 2. context-strategy OPE v2 from scaled per-task solved + context_need
    cells = []
    for task, by_policy in arena["per_task_solved"].items():
        need = need_by_task.get(task, "unknown")
        for pol, solved in by_policy.items():
            strat = _POLICY_TO_STRATEGY.get(pol)
            if strat:
                cells.append({"context_need": need, "strategy": strat, "solved": solved,
                              "cost_usd": 0.002, "conclusive": True})
    ope = ContextStrategyOPE(min_samples=3).fit(cells)
    ope_report = ope.to_report()
    # attach Wilson CIs per (need, best strategy)
    for need, rec in ope_report["recommendations"].items():
        if rec.get("recommended"):
            rows = [c for c in cells if c["context_need"] == need
                    and c["strategy"] == rec["recommended"]]
            succ = sum(1 for c in rows if c["solved"])
            rec["wilson_ci"] = dict(zip(("point", "lo", "hi"),
                                        wilson_ci(succ, len(rows)), strict=False))
    ope_report["experiment"] = "context_strategy_ope_v2"
    (ROOT / "reports" / "context_strategy_ope_v2.json").write_text(
        json.dumps(ope_report, indent=2) + "\n")

    # 3. finops marginal value — representative escalation ladder on a cross-file task
    ctl = MarginalValueController(budget_class="cross_file_bugfix")
    ctl.should_spend(p_now=0.0, p_after=0.6, step_cost=0.0015, label="repo_map_context")
    ctl.should_spend(p_now=0.6, p_after=0.8, step_cost=0.002, label="advisor")
    ctl.should_spend(p_now=0.8, p_after=0.82, step_cost=0.01, label="best_of_k_extra")  # low value
    fin = {"experiment": "finops_marginal_value", **ctl.report(),
           "note": "spends only while expected marginal value is positive within budget"}
    (ROOT / "reports" / "finops_marginal_value.json").write_text(json.dumps(fin, indent=2) + "\n")

    print("policy ranking (scaled):", [s["policy"] for s in ranked])
    print("context_ope_v2:", {k: v.get("recommended") for k, v in
                              ope_report["recommendations"].items()})
    print("finops ladder proceeded steps:", ctl.report()["n_proceeded"], "/ 3")
    print("wrote scaled artifacts: policy_compare + context_ope_v2 + finops_marginal_value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
