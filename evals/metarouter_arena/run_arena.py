"""MetaRouter Arena runner (GOALS Alpha 42 P0).

Runs the unseen task pack across competing policies and writes the arena report +
policy-comparison, separating adapter availability from capability and computing verified
success per dollar. Live policies use the reachable Claude adapter/harness; deterministic
floor/oracle baselines always run. Skips live policies cleanly without a key.

    uv run python evals/metarouter_arena/run_arena.py [--full]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from evals.metarouter_arena.policies import (  # noqa: E402
    ALL_POLICIES,
    advisor_fn,
)
from evals.metarouter_arena.schema import AdapterStatus, PolicyScore  # noqa: E402
from evals.metarouter_arena.task_pack import TASK_PACK  # noqa: E402

from acp.observability.live_report import redact_report  # noqa: E402

# Bounded default policy set (live-affordable smoke); --full adds best_of_k + advisor.
DEFAULT_POLICIES = ["cheap_static", "oracle", "cheap_single", "repo_map_router", "claude_harness"]
FULL_POLICIES = DEFAULT_POLICIES + ["advisor_router", "best_of_k_router"]


def _claude_adapters():
    single = harness = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
        from acp.agents.claude_agent import ClaudeAgentAdapter
        from acp.agents.claude_harness import ClaudeHarnessAdapter
        s = ClaudeAgentAdapter(model="claude-sonnet-4-6")
        if asyncio.run(s.healthcheck()).available:
            single = s
        h = ClaudeHarnessAdapter(max_steps=6)
        if asyncio.run(h.healthcheck()).available:
            harness = h
    return single, harness


def main() -> int:
    full = "--full" in sys.argv
    policy_names = FULL_POLICIES if full else DEFAULT_POLICIES
    claude_single, claude_harness = _claude_adapters()
    advise = advisor_fn(claude_single) if claude_single else None

    scores: dict[str, PolicyScore] = {p: PolicyScore(policy=p) for p in policy_names}
    attempts: list[dict] = []
    per_task: dict[str, dict[str, bool]] = {}
    with tempfile.TemporaryDirectory(prefix="acp_arena_") as d:
        root = Path(d)
        for spec in TASK_PACK:
            per_task[spec.name] = {}
            for pname in policy_names:
                fn = ALL_POLICIES[pname]
                att = fn(spec, root, claude_single=claude_single,
                         claude_harness=claude_harness, advise=advise)
                scores[pname].add(att)
                attempts.append(att.to_dict())
                per_task[spec.name][pname] = att.solved
                flag = "OK " if att.solved else ("·· " if att.conclusive else "?? ")
                print(f"  {spec.name:18s} {pname:18s} {flag} "
                      f"status={att.adapter_status} cost=${att.cost_usd}")

    # routing-regret vs oracle + repo_map reproduction across task families
    oracle_solved = {t: v.get("oracle", False) for t, v in per_task.items()}
    n_oracle = sum(1 for s in oracle_solved.values() if s)
    repo_map_wins = [t for t, v in per_task.items()
                     if v.get("repo_map_router") and not v.get("cheap_single")]
    cheap_wins_over_map = [t for t, v in per_task.items()
                           if v.get("cheap_single") and not v.get("repo_map_router")]

    report = {
        "experiment": "metarouter_arena",
        "round": "Alpha 42 — Evidence-Driven MetaRouter",
        "n_tasks": len(TASK_PACK),
        "policies": policy_names,
        "live_claude_single": claude_single is not None,
        "live_claude_harness": claude_harness is not None,
        "adapter_status_legend": [s.value for s in AdapterStatus],
        "policy_scores": [scores[p].to_dict() for p in policy_names],
        "routing_signal": {
            "oracle_solvable": n_oracle,
            "repo_map_wins_over_cheap": repo_map_wins,
            "repo_map_reproduced_in_n_families": len(repo_map_wins),
            "cheap_wins_over_repo_map": cheap_wins_over_map,
        },
        "per_task_solved": per_task,
        "attempts": attempts,
        "evidence_tier": "fixture-unseen (authored for the arena); live Claude where available",
        "note": ("smoke-scale conclusive cells; the >=300-cell acceptance gate needs a larger "
                 "live budget. Availability is separated from capability per Alpha-42 P0."),
    }
    out = _ROOT / "reports" / "metarouter_arena.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    # policy comparison (sorted by verified success per dollar, then verified rate)
    compare = sorted(report["policy_scores"],
                     key=lambda s: (-(s["verified_success_rate"]),
                                    s["cost_per_verified_success"] or 9e9))
    (out.parent / "metarouter_policy_compare.json").write_text(json.dumps(
        {"experiment": "metarouter_policy_compare", "ranking": compare}, indent=2) + "\n")
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"

    print("\n=== policy ranking (verified success / $) ===")
    for s in compare:
        print(f"  {s['policy']:18s} verified={s['verified_success_rate']:.2f} "
              f"conclusive={s['conclusive_rate']:.2f} cost/success="
              f"{s['cost_per_verified_success']} unavail={s['adapter_unavailable_rate']:.2f}")
    print(f"\nrepo_map reproduced wins in {len(repo_map_wins)} task families: {repo_map_wins}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
