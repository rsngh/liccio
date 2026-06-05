"""HeavySkill live demonstration (Alpha 24 area 11).

Runs the parallel-deliberation skill over the graded benchmark with a live weak model
(k samples each), showing: engagement (easy/low-risk single-shot vs medium/hard engaged),
self-consistency pruning savings before verification, and solve rate. Writes
heavyskill_bugfix.json and parallel_deliberation_skill.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.agents.weak_model_candidates import DEFAULT_WEAK_MODEL, openai_sampler
from acp.core.config import get_settings
from acp.observability.live_report import redact_report
from acp.training.heavy_skill import heavy_skill_solve

K = 5


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    sampler = openai_sampler(model=DEFAULT_WEAK_MODEL, temperature=0.9)
    rows = []
    for task in BENCH_TASKS:
        r = heavy_skill_solve(task, sampler=sampler, k=K, risk="low")
        r.candidates = []
        rows.append(r.to_dict())
        print(f"{task.name:16s} engaged={r.engaged} solved={r.solved} "
              f"verified={r.n_verified}/{r.n_sampled} savings={r.verify_savings_fraction}")
    engaged = [r for r in rows if r["engaged"]]
    bugfix = {"experiment": "heavyskill_bugfix", "model": DEFAULT_WEAK_MODEL, "k": K,
              "rows": rows,
              "engaged_solve_rate": round(
                  sum(r["solved"] for r in engaged) / len(engaged), 4) if engaged else None,
              "single_shot_tasks": [r["task_name"] for r in rows if not r["engaged"]]}
    skill = {"experiment": "parallel_deliberation_skill", "k": K,
             "mean_verify_savings": round(
                 sum(r["verify_savings_fraction"] for r in engaged) / len(engaged), 4)
             if engaged else 0.0,
             "engages_on": ["medium", "hard", "high_risk"],
             "single_shot_on": ["easy_low_risk"]}
    for name, data in (("heavyskill_bugfix.json", bugfix),
                       ("parallel_deliberation_skill.json", skill)):
        out = Path("evals/reports") / name
        out.write_text(json.dumps(redact_report(data), indent=2) + "\n")
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            secret = os.environ.get(key)
            if secret:
                assert secret not in out.read_text(), f"{key} leaked!"
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
