"""Vendor + SkillOpt live canary (Alpha 22 WS16).

Runs a candidate skill through a real vendor-native harness (Claude Code, which drives
headlessly in seconds) on the no-patch smoke fixture: baseline (no skill) vs candidate
(verify skill) arms, conclusive attempts only, then the A/B + Bayesian canary gate decides
promote / rollback / abstain. Writes reports/live/vendor_skill_canary.json (redacted).

Usage: ensure `claude` is on PATH; `uv run python evals/scripts/run_vendor_skill_canary_live.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from acp.agents.vendor_native import VendorNativeHarness, build_smoke_fixture
from acp.observability.live_report import redact_report
from acp.training.skill_canary import bayesian_canary, evaluate_ab_canary

SKILL = ("# bugfix skill\n"
         "- After editing, run the project's tests and fix any failures before finishing.\n")
REPS = 3
HARNESS = "claude_code"  # headless + fast


def _arm(harness: VendorNativeHarness, skill: str | None) -> list[dict]:
    cells = []
    for _ in range(REPS):
        with tempfile.TemporaryDirectory() as d:
            repo = build_smoke_fixture(Path(d))
            res = harness.run_smoke(repo, timeout_s=180, skill_content=skill)
            cells.append(res.to_cell())
    return cells


def main() -> int:
    if shutil.which("claude") is None:
        print("[skip] claude (Claude Code) not on PATH")
        return 0
    harness = VendorNativeHarness(HARNESS)
    control = _arm(harness, None)
    canary = _arm(harness, SKILL)
    ab = evaluate_ab_canary(control, canary, min_per_arm=2)
    bayes = bayesian_canary(control, canary, min_per_arm=2)
    decision = ("promote" if ab.promote else
                ("abstain" if (ab.canary_n < 2 or ab.contaminated) else "hold"))
    report = {
        "experiment": "ws16_vendor_skill_canary", "harness": HARNESS, "skill": SKILL,
        "control_rate": ab.control_rate, "canary_rate": ab.canary_rate,
        "control_n": ab.control_n, "canary_n": ab.canary_n, "lift": ab.lift,
        "p_value": ab.p_value, "prob_canary_better": bayes.prob_canary_better,
        "contaminated": ab.contaminated, "promote": ab.promote, "decision": decision,
        "reasons": ab.reasons,
    }
    out = Path("reports/live/vendor_skill_canary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"vendor skill canary [{HARNESS}]: control={ab.control_rate} canary={ab.canary_rate} "
          f"lift={ab.lift} P(better)={bayes.prob_canary_better} decision={decision}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
