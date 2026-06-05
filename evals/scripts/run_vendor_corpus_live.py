"""Vendor-native corpus campaign (Alpha 26) — activation-aware, measurement-trusted.

Runs the Claude Code vendor harness across the full task corpus (graded easy/medium/hard +
the hard greedy-trap cohort), baseline vs the full-suite-discipline skill, and records
PER-TASK activation (did the harness actually edit anything) for BOTH arms.

Measurement-trust guard (added after a no-op claude_code run was nearly misread as negative
transfer): a vendor attempt with no diff and no solve is a HARNESS-ACTIVATION failure, which
is infra/inconclusive — NOT a skill/capability failure. A skill-lift number is only trusted
when BOTH arms actually activated on most tasks (activation_rate high). If the with-skill arm
mostly failed to activate (CLI degraded/rate-limited), the run is flagged untrusted and no
negative-transfer claim is made. Writes evals/reports/vendor_capability_matrix.json.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS, build_bench_repo
from acp.agents.hard_tasks import HARD_TASKS
from acp.agents.vendor_native import VendorNativeHarness
from acp.observability.live_report import redact_report

HARNESS = "claude_code"
CORPUS = BENCH_TASKS + HARD_TASKS
SKILL = ("# full-suite discipline\n- Run the FULL pytest suite and fix EVERY failing test; "
         "for algorithmic bugs prefer a correct dynamic-programming solution over greedy.\n")
MIN_ACTIVATION = 0.8   # below this, the arm did not really run -> result untrusted


def _run_arm(harness, skill):
    rows = []
    for task in CORPUS:
        with tempfile.TemporaryDirectory() as d:
            repo = build_bench_repo(Path(d), task)
            r = harness.run_task(repo, task.prompt, task_type=task.difficulty,
                                 task_name=task.name, timeout_s=240, skill_content=skill)
        # activation = the harness actually did work (edited or solved), not a no-op return
        activated = bool(r.diff_captured or r.no_patch_solve)
        rows.append({"task": task.name, "difficulty": task.difficulty,
                     "solved": r.no_patch_solve, "activated": activated,
                     "outcome": r.outcome, "wall_time_s": r.wall_time_s})
    activation_rate = round(sum(x["activated"] for x in rows) / len(rows), 4)
    # solve rate over attempts where the harness actually activated (conclusive task signal)
    active = [x for x in rows if x["activated"]]
    solve_rate = round(sum(x["solved"] for x in active) / len(active), 4) if active else 0.0
    return {"rows": rows, "activation_rate": activation_rate, "solve_rate": solve_rate,
            "n_activated": len(active)}


def main() -> int:
    if shutil.which("claude") is None:
        print("[skip] claude (Claude Code) not on PATH")
        return 0
    harness = VendorNativeHarness(HARNESS)
    baseline = _run_arm(harness, None)
    skilled = _run_arm(harness, SKILL)
    both_activated = (baseline["activation_rate"] >= MIN_ACTIVATION
                      and skilled["activation_rate"] >= MIN_ACTIVATION)
    report = {
        "experiment": "vendor_capability_matrix", "harness": HARNESS, "n_tasks": len(CORPUS),
        "baseline": baseline, "with_skill": skilled,
        "skill_lift_active_only": round(skilled["solve_rate"] - baseline["solve_rate"], 4),
        "both_arms_activated": both_activated,
        # Only trust a skill-lift (esp. a negative one) when both arms actually ran.
        "skill_lift_trusted": both_activated,
        "caveat": (None if both_activated else
                   "low activation in >=1 arm (CLI degraded/rate-limited) -> lift untrusted, "
                   "treated as infra/inconclusive, NOT negative transfer"),
    }
    out = Path("evals/reports/vendor_capability_matrix.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"vendor [{HARNESS}] n={len(CORPUS)}: baseline activation="
          f"{baseline['activation_rate']} solve={baseline['solve_rate']} | "
          f"skill activation={skilled['activation_rate']} solve={skilled['solve_rate']}")
    print(f"both_arms_activated={both_activated} skill_lift_trusted={report['skill_lift_trusted']}")
    if not both_activated:
        print(f"CAVEAT: {report['caveat']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
