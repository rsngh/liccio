"""Cross-harness skill transfer (Round 16) — does an openai-optimized skill help claude?

The SkillOpt paper reports large cross-harness transfer. This measures it live: take the
compact skill optimized on openai_harness ("run tests before finishing") and evaluate a
WEAKENED claude_harness on a held-out task split with and without the skill injected. The
transfer gain = with_skill_score - baseline_score. Real rollouts, repo-pytest verified,
bounded spend, redacted artifact.

Usage: set OPENAI_API_KEY + ANTHROPIC_API_KEY, then run this script with `uv run python`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_live_bakeoff as B  # noqa: E402
from run_skillopt_live import _run_task_with_skill  # noqa: E402

from acp.observability.live_report import redact_report  # noqa: E402

# The compact skill SkillOpt accepted on the weak openai harness (held-out 0.5 -> 1.0).
TRANSFER_SKILL = (
    "# Coding skill\n"
    "- After editing, ALWAYS run the project's tests and fix failures before finishing.\n")

# Harder held-out tasks (headroom for a weak harness).
HELD_OUT_IDS = ["testgen_stats", "feature_lru_cache", "bugfix_fib"]


def _score(adapter, specs, skill_content: str) -> float:
    solved = 0
    for spec in specs:
        with tempfile.TemporaryDirectory() as d:
            if _run_task_with_skill(adapter, spec, skill_content, Path(d)):
                solved += 1
    return round(solved / len(specs), 4) if specs else 0.0


def main() -> int:
    from acp.agents.claude_harness import ClaudeHarnessAdapter
    adapters = B._build_adapters()
    if "claude_harness" not in adapters:
        print("[skip] claude_harness unavailable (set ANTHROPIC_API_KEY)")
        return 0
    # Weakened target harness so the procedural skill has headroom to transfer.
    target = ClaudeHarnessAdapter(max_steps=3)
    specs = [s for s in B.TASKS if s["id"] in HELD_OUT_IDS]
    baseline = _score(target, specs, "")
    with_skill = _score(target, specs, TRANSFER_SKILL)
    gain = round(with_skill - baseline, 4)
    report = {
        "experiment": "round16_skill_transfer_live",
        "source_harness": "openai_harness",
        "target_harness": "claude_harness",
        "skill": TRANSFER_SKILL,
        "held_out_size": len(specs),
        "baseline_score": baseline,
        "with_skill_score": with_skill,
        "transfer_gain": gain,
        "transferred": gain > 0,
    }
    out = Path("reports/live/skill_transfer.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"transfer openai->claude: baseline={baseline} with_skill={with_skill} "
          f"gain={gain} transferred={gain > 0}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
