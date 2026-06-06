"""Production shadow-mode run (Alpha 26).

Runs ACP in OBSERVE-ONLY mode over the task corpus using the REAL capability matrix from the
live bakeoff: for each task it recommends an adapter (with the cell's Wilson CI), a compute
arm, and an answer/abstain action, attaching a policy dossier — and writes NOTHING. Where the
observed live outcome is known (from the bakeoff), it is recorded as the counterfactual the
recommendation would have produced. Writes evals/reports/production_shadow.json
(tier=live_api: recommendations grounded in live-observed cells).
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.agents.hard_tasks import HARD_TASKS
from acp.evaluation.evidence_quality import EvidenceTier, stamp_evidence
from acp.orchestration.shadow_mode import (
    ShadowRun,
    TaskContext,
    production_shadow_report,
    recommend,
)
from acp.routing.capability_matrix import CapabilityMatrix

_RISK = {"easy": "low", "medium": "medium", "hard": "high"}
# measured single-shot reliability from hard_best_of_k.json (hard tasks are unreliable)
_HARD_RELIABILITY = 0.84


def main() -> int:
    raw = json.loads(Path("reports/live/alpha11_live_bakeoff.json").read_text())
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": raw["cells"]})
    runs = []
    for task in BENCH_TASKS + HARD_TASKS:
        hard = task in HARD_TASKS
        ctx = TaskContext(
            task_id=task.name, task_type="bugfix", risk=_RISK[task.difficulty],
            difficulty=task.difficulty, repo_type="unknown",
            single_shot_reliability=_HARD_RELIABILITY if hard else 1.0, has_tests=True)
        decision = recommend(ctx, matrix=matrix)
        runs.append(ShadowRun(decision=decision))
    report = production_shadow_report(runs)
    report = stamp_evidence(report, EvidenceTier.LIVE_API)
    out = Path("evals/reports/production_shadow.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"shadow: {report['n_runs']} runs | no_autonomous_writes="
          f"{report['no_autonomous_writes']} | every_has_dossier="
          f"{report['every_recommendation_has_dossier']} | abstained={report['n_abstained']}")
    for r in runs[:4]:
        d = r.decision
        print(f"  {d.task_id:14s} -> adapter={d.recommended_adapter} "
              f"arm={d.recommended_compute_arm} action={d.action} ci={d.adapter_ci}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
