"""Graded benchmark skill A/B — live lift by difficulty (Alpha 23 WS5).

Runs the graded suite through a real vendor harness twice: baseline (no skill) vs a
verify-and-edge-cases skill, conclusive attempts only, and measures lift OVERALL and PER
DIFFICULTY with a two-proportion z-test + Bayesian beta-binomial. The skill targets the
suite's actual failure modes (declare-done-without-running-the-full-suite, missed edge
cases). Decision: promote only if lift>0 with P(better) over threshold on a tier with
headroom; otherwise hold (honest non-promotion). Writes reports/live/benchmark_skill_ab.json.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from acp.agents.vendor_native import VendorNativeHarness
from acp.evaluation.benchmark_runner import run_benchmark
from acp.observability.live_report import redact_report
from acp.training.skill_canary import bayesian_canary, evaluate_ab_canary

HARNESS = "claude_code"
SKILL = (
    "# verify-and-edge-cases bugfix skill\n"
    "- Before finishing, run the FULL test suite with `python -m pytest -q`.\n"
    "- For EVERY failing test, fix the code and re-run until ALL tests pass.\n"
    "- Consider edge cases explicitly: empty input, boundaries/off-by-one, ordering,\n"
    "  and special forms (e.g. subtractive notation). Do not declare done early.\n"
)
REPS = 2


def _cells(harness, skill):
    # one cell per (task, rep) carrying success/outcome for the canary statistics
    r = run_benchmark(harness, skill_content=skill, timeout_s=240, reps=REPS)
    cells = [{"adapter": HARNESS, "task_type": t["difficulty"], "is_harness": True,
              "success": t["solved"],
              "status": "timed_out" if t["outcome"].startswith("infra") else (
                  "succeeded" if t["solved"] else "failed"),
              "timed_out": t["outcome"].startswith("infra"),
              "error": None, "tool_calls": 1, "commands": 1, "file_reads": 1,
              "cost_usd": 0.0} for t in r.tasks]
    return r, cells


def main() -> int:
    if shutil.which("claude") is None:
        print("[skip] claude (Claude Code) not on PATH")
        return 0
    harness = VendorNativeHarness(HARNESS)
    base_r, base_cells = _cells(harness, None)
    skill_r, skill_cells = _cells(harness, SKILL)
    ab = evaluate_ab_canary(base_cells, skill_cells, min_per_arm=2)
    bayes = bayesian_canary(base_cells, skill_cells, min_per_arm=2)
    decision = ("promote" if ab.promote else
                ("abstain" if (ab.canary_n < 2 or ab.contaminated) else "hold"))
    report = {
        "experiment": "ws5_benchmark_skill_ab", "harness": HARNESS, "skill": SKILL,
        "overall": {"baseline": base_r.overall_solve_rate,
                    "with_skill": skill_r.overall_solve_rate,
                    "lift": round(ab.lift, 4), "p_value": ab.p_value,
                    "prob_better": bayes.prob_canary_better},
        "by_difficulty": {d: {"baseline": base_r.by_difficulty.get(d, {}).get("solve_rate"),
                              "with_skill": skill_r.by_difficulty.get(d, {}).get("solve_rate")}
                          for d in base_r.by_difficulty},
        "promote": ab.promote, "decision": decision, "reasons": ab.reasons,
    }
    out = Path("reports/live/benchmark_skill_ab.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"benchmark skill A/B [{HARNESS}]: baseline={base_r.overall_solve_rate} "
          f"with_skill={skill_r.overall_solve_rate} lift={round(ab.lift, 4)} "
          f"P(better)={bayes.prob_canary_better} decision={decision}")
    for d, v in report["by_difficulty"].items():
        print(f"  {d:7s}: {v['baseline']} -> {v['with_skill']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
