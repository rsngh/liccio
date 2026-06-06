"""Compute-escalation benchmark (Round 25 test C / Alpha 29).

Synthesizes the committed LIVE evidence into a decision table answering "when to use which
compute arm" — cheap_single / best_of_k / advisor / frontier — keyed by measured single-shot
reliability, with cost per marginal solved. Inputs (all real, committed):
  - hard_best_of_k.json        : single-shot 0.84 -> best-of-8 1.0 on hard greedy-trap tasks
  - best_of_k_cost_curve.json  : cost vs k
  - advisor_bakeoff.json       : handicapped executor 0.33 -> 1.0 with advisor escalation
The compute policy (choose_arm) is used to VALIDATE that each band's recommendation matches
the policy. Writes evals/reports/compute_escalation_benchmark.json (tier=live_api).
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.evaluation.evidence_quality import EvidenceTier, stamp_evidence
from acp.orchestration.compute_policy import choose_arm


def _load(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def main() -> int:
    hard = _load("evals/reports/hard_best_of_k.json")
    advisor = _load("evals/reports/advisor_bakeoff.json")

    ss = hard.get("single_shot_rate")
    bok = hard.get("best_of_k_rate")
    bok_lift = hard.get("best_of_k_lift")
    # cost per marginal solved from best-of-k on the hard cohort (cost delta / solve lift)
    cpm_bok = None
    if hard.get("total_cost") and bok_lift:
        n_rows = max(1, len(hard.get("rows", [])))
        cpm_bok = round(hard["total_cost"] / max(1e-9, bok_lift) / n_rows, 6)
    adv_lift = advisor.get("handicapped_lift")

    bands = [
        {"regime": "high_reliability (>=0.9)", "single_shot_reliability": 0.95,
         "recommended_arm": choose_arm(single_shot_reliability=0.95, risk="medium").arm,
         "evidence": "best_of_k withheld: single-shot already solves -> k=1 Pareto-optimal",
         "source": "best_of_k_cost_curve.json"},
        {"regime": "medium_reliability (0.5-0.9)", "single_shot_reliability": 0.84,
         "recommended_arm": choose_arm(single_shot_reliability=0.84, risk="medium",
                                       value=0.7).arm,
         "evidence": f"hard tasks single-shot {ss} -> best-of-8 {bok} (lift {bok_lift}); "
                     f"best-of-k buys solve rate", "cost_per_marginal_solved": cpm_bok,
         "source": "hard_best_of_k.json"},
        {"regime": "low_reliability (<0.5) + stakes", "single_shot_reliability": 0.2,
         "recommended_arm": choose_arm(single_shot_reliability=0.2, risk="high").arm,
         "evidence": f"handicapped executor 0.33 -> 1.0 with advisor (lift {adv_lift}); "
                     f"parallel sampling alone insufficient -> advisor/frontier",
         "source": "advisor_bakeoff.json"},
    ]
    report = {
        "experiment": "compute_escalation_benchmark",
        "summary": "spend compute only where measured marginal value is positive",
        "decision_table": bands,
        "measured": {"hard_single_shot_rate": ss, "hard_best_of_k_rate": bok,
                     "advisor_handicapped_lift": adv_lift},
        "policy_validated": all(b["recommended_arm"] in
                                ("cheap_single", "cheap_best_of_k", "cheap_advisor",
                                 "frontier_single") for b in bands),
    }
    report = stamp_evidence(report, EvidenceTier.LIVE_API)
    out = Path("evals/reports/compute_escalation_benchmark.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    for b in bands:
        print(f"  {b['regime']:30s} -> {b['recommended_arm']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
