"""Underspecified-task skill A/B — live (Alpha 23 WS10).

The decisive skill-value experiment: each task has two bugs but the prompt names only one.
Arm A (baseline) gets the underspecified prompt alone; arm B also gets a "run the FULL
suite and fix EVERY failure" skill. If the skill lifts solve rate the gap is attributable
to test discipline (NOT timeout pressure — the second bug is genuinely present), so the
governance can promote. Otherwise it holds. reps default 3 for a usable arm size.
Writes reports/live/underspecified_skill_ab.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import UNDERSPECIFIED_TASKS, build_bench_repo
from acp.agents.vendor_native import VendorNativeHarness
from acp.observability.live_report import redact_report
from acp.training.skill_canary import bayesian_canary, evaluate_ab_canary

HARNESS = "claude_code"
REPS = 3
TIMEOUT_S = 240
SKILL = (
    "# full-suite discipline skill\n"
    "- The task may mention ONE failing test, but other tests can also be broken.\n"
    "- Always run the FULL suite with `python -m pytest -q` and fix EVERY failing test,\n"
    "  not just the one named, before finishing.\n"
)


def _arm(harness: VendorNativeHarness, skill: str | None) -> list[dict]:
    cells: list[dict] = []
    for task in UNDERSPECIFIED_TASKS:
        for _ in range(REPS):
            with tempfile.TemporaryDirectory() as d:
                repo = build_bench_repo(Path(d), task)
                res = harness.run_task(repo, task.prompt, task_type=task.difficulty,
                                       task_name=task.name, timeout_s=TIMEOUT_S,
                                       skill_content=skill)
            cells.append(res.to_cell())
    return cells


def _rate(cells: list[dict]) -> float:
    ok = [c for c in cells if c["status"] in ("succeeded", "failed")]
    return round(sum(c["success"] for c in ok) / len(ok), 4) if ok else 0.0


def main() -> int:
    if shutil.which("claude") is None:
        print("[skip] claude (Claude Code) not on PATH")
        return 0
    harness = VendorNativeHarness(HARNESS)
    base = _arm(harness, None)
    skilled = _arm(harness, SKILL)
    ab = evaluate_ab_canary(base, skilled, min_per_arm=3)
    bayes = bayesian_canary(base, skilled, min_per_arm=3)
    decision = ("promote" if ab.promote else
                ("abstain" if (ab.canary_n < 3 or ab.contaminated) else "hold"))
    report = {
        "experiment": "ws10_underspecified_skill_ab", "harness": HARNESS, "skill": SKILL,
        "baseline_rate": _rate(base), "skill_rate": _rate(skilled),
        "control_n": ab.control_n, "canary_n": ab.canary_n, "lift": round(ab.lift, 4),
        "p_value": ab.p_value, "prob_better": bayes.prob_canary_better,
        "contaminated": ab.contaminated, "promote": ab.promote, "decision": decision,
        "reasons": ab.reasons,
    }
    out = Path("reports/live/underspecified_skill_ab.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"underspecified skill A/B [{HARNESS}]: baseline={report['baseline_rate']} "
          f"skill={report['skill_rate']} lift={report['lift']} "
          f"P(better)={bayes.prob_canary_better} decision={decision}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
