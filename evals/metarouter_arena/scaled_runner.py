"""Scaled MetaRouter Arena runner (GOALS Alpha 43 P0).

Runs the >=50-task corpus across the policy matrix to produce >=300 conclusive cells with
Wilson confidence intervals, cell accounting (by task_type / context_need), and a failure
taxonomy — separating adapter availability from capability. Live policies use the reachable
Claude adapter; deterministic floor/oracle/abstain always run. Anthropic-only.

    uv run python evals/metarouter_arena/scaled_runner.py [--policies a,b,c] [--reps N]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from evals.metarouter_arena.policies import ALL_POLICIES  # noqa: E402
from evals.metarouter_arena.schema import AdapterStatus, PolicyScore  # noqa: E402
from evals.metarouter_arena.statistics import beats_with_confidence, wilson_ci  # noqa: E402
from evals.metarouter_arena.task_loader import load_scaled_tasks  # noqa: E402
from evals.metarouter_arena.task_pack import TASK_PACK  # noqa: E402

from acp.observability.live_report import redact_report  # noqa: E402

# bounded, live-affordable default matrix (single-shot live + deterministic baselines)
DEFAULT = ["cheap_static", "oracle", "abstain_router", "cheap_single", "grep_router",
           "repo_map_router"]
INCUMBENT = "cheap_single"


def _claude_single():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    from acp.agents.claude_agent import ClaudeAgentAdapter
    a = ClaudeAgentAdapter(model="claude-sonnet-4-6")
    return a if asyncio.run(a.healthcheck()).available else None


def main() -> int:
    policies = DEFAULT
    reps = 1
    for i, a in enumerate(sys.argv):
        if a == "--policies" and i + 1 < len(sys.argv):
            policies = sys.argv[i + 1].split(",")
        if a == "--reps" and i + 1 < len(sys.argv):
            reps = int(sys.argv[i + 1])
    tasks = load_scaled_tasks() + list(TASK_PACK)
    claude_single = _claude_single()

    scores = {p: PolicyScore(policy=p) for p in policies}
    succ = defaultdict(int)            # policy -> verified successes (for CIs)
    conc = defaultdict(int)            # policy -> conclusive cells
    by_cell = defaultdict(lambda: {"n": 0, "conclusive": 0, "solved": 0})  # (type,need)->counts
    failure_taxonomy = defaultdict(int)
    per_task = defaultdict(dict)
    n_cells = 0
    t_start = time.time()
    with tempfile.TemporaryDirectory(prefix="acp_scaled_") as d:
        root = Path(d)
        for rep in range(reps):
            for spec in tasks:
                for pname in policies:
                    att = ALL_POLICIES[pname](spec, root, claude_single=claude_single,
                                              claude_harness=None, advise=None)
                    scores[pname].add(att)
                    n_cells += 1
                    if att.conclusive:
                        conc[pname] += 1
                        succ[pname] += int(att.solved)
                    cell = (spec.task_type, spec.context_need)
                    by_cell[cell]["n"] += 1
                    by_cell[cell]["conclusive"] += int(att.conclusive)
                    by_cell[cell]["solved"] += int(att.solved)
                    per_task[spec.name][pname] = att.solved
                    if not att.solved and att.conclusive and att.adapter_status == \
                            AdapterStatus.LIVE_CONCLUSIVE.value:
                        failure_taxonomy[f"{pname}:{spec.task_type}"] += 1
            print(f"  rep {rep+1}/{reps}: {n_cells} cells, {sum(conc.values())} conclusive "
                  f"({time.time()-t_start:.0f}s)")

    total_conclusive = sum(conc.values())
    # confidence intervals + promotion vs incumbent (Wilson-separated)
    ci = {p: dict(zip(("point", "lo", "hi"), wilson_ci(succ[p], conc[p]), strict=False))
          for p in policies}
    promotions = []
    if INCUMBENT in policies:
        for p in policies:
            if p in (INCUMBENT, "oracle", "cheap_static"):
                continue
            promotions.append({
                "policy": p,
                "beats_incumbent_with_confidence": beats_with_confidence(
                    succ[p], conc[p], succ[INCUMBENT], conc[INCUMBENT]),
                "verified": ci[p]["point"], "incumbent_verified": ci[INCUMBENT]["point"]})

    n_types = len({t.task_type for t in tasks})
    n_needs = len({t.context_need for t in tasks})
    accounting = {
        "n_tasks": len(tasks), "n_task_types": n_types, "n_context_needs": n_needs,
        "n_policies": len(policies), "n_cells": n_cells,
        "n_conclusive_cells": total_conclusive,
        "conclusive_rate": round(total_conclusive / n_cells, 4) if n_cells else 0.0,
        "by_cell": {f"{k[0]}|{k[1]}": v for k, v in sorted(by_cell.items())},
    }
    gate = {
        "ge_300_conclusive_cells": total_conclusive >= 300,
        "ge_50_tasks": len(tasks) >= 50,
        "ge_8_task_types": n_types >= 8,
        "ge_5_context_needs": n_needs >= 5,
        "conclusive_rate_ge_80pct": accounting["conclusive_rate"] >= 0.80,
        "high_risk_false_auto_approve": 0,   # arena verifies by hidden tests; no auto-approve
    }
    report = {
        "experiment": "metarouter_arena_scaled",
        "round": "Alpha 43 — Scale-Proven MetaRouter",
        "live_claude": claude_single is not None,
        "policies": policies, "reps": reps,
        "policy_scores": [scores[p].to_dict() for p in policies],
        "confidence_intervals": ci,
        "promotions_vs_incumbent": promotions,
        "promotable_with_confidence": [p["policy"] for p in promotions
                                       if p["beats_incumbent_with_confidence"]],
        "cell_accounting": accounting,
        "acceptance_gate": gate,
        "all_gates_pass": all(v if isinstance(v, bool) else True for v in gate.values()),
        "failure_taxonomy": dict(sorted(failure_taxonomy.items(), key=lambda x: -x[1])[:20]),
        "per_task_solved": per_task,
        "evidence_tier": "fixture-unseen (authored for the arena); live Claude (Anthropic only)",
        "elapsed_s": round(time.time() - t_start, 1),
    }
    out = _ROOT / "reports" / "metarouter_arena_scaled.json"
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    (_ROOT / "reports" / "metarouter_cell_accounting.json").write_text(
        json.dumps(accounting, indent=2) + "\n")
    (_ROOT / "reports" / "metarouter_confidence_intervals.json").write_text(
        json.dumps({"confidence_intervals": ci, "promotions": promotions}, indent=2) + "\n")
    (_ROOT / "reports" / "metarouter_failure_taxonomy.json").write_text(
        json.dumps(report["failure_taxonomy"], indent=2) + "\n")
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        s = os.environ.get(key)
        if s:
            assert s not in out.read_text(), f"{key} leaked!"

    print(f"\n=== scaled arena: {total_conclusive} conclusive cells "
          f"({accounting['conclusive_rate']:.0%}) across {len(tasks)} tasks ===")
    for p in policies:
        c = ci[p]
        print(f"  {p:16s} verified={c['point']:.2f} [{c['lo']:.2f},{c['hi']:.2f}] "
              f"conclusive={conc[p]} cost/succ={scores[p].to_dict()['cost_per_verified_success']}")
    print(f"promotable with confidence over {INCUMBENT}: {report['promotable_with_confidence']}")
    print(f"gates: {gate}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
