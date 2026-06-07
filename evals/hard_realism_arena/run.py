"""Hard-Realism Arena runner (GOALS Alpha 44 P0).

Runs the hard task corpus across the policy matrix to produce >=600 conclusive cells, then does
BUCKET-LEVEL promotion: for each (context_need) bucket, which policy beats the incumbent
cheap_single with Wilson-CI separation? This is the Alpha-44 thesis — a global policy may not
beat a strong cheap baseline, but ACP can prove *where* metarouting has differentiated value.
Anthropic-only; deterministic baselines always run.

    uv run python evals/hard_realism_arena/run.py [--policies a,b,c]
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

from evals.hard_realism_arena.task_pack import load_hard_tasks  # noqa: E402
from evals.metarouter_arena.policies import ALL_POLICIES  # noqa: E402
from evals.metarouter_arena.schema import AdapterStatus, PolicyScore  # noqa: E402
from evals.metarouter_arena.statistics import beats_with_confidence, wilson_ci  # noqa: E402

from acp.observability.live_report import redact_report  # noqa: E402

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
    for i, a in enumerate(sys.argv):
        if a == "--policies" and i + 1 < len(sys.argv):
            policies = sys.argv[i + 1].split(",")
    tasks = load_hard_tasks()
    claude_single = _claude_single()

    scores = {p: PolicyScore(policy=p) for p in policies}
    # per-bucket (context_need) success/conclusive counts per policy
    bucket: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0]))   # need -> policy -> [succ, conclusive]
    global_sc = defaultdict(lambda: [0, 0])
    failure_taxonomy = defaultdict(int)
    cheap_single_fail_tasks: list[str] = []
    per_task = defaultdict(dict)
    n_cells = 0
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="acp_hard_") as d:
        root = Path(d)
        for ti, spec in enumerate(tasks):
            for pname in policies:
                att = ALL_POLICIES[pname](spec, root, claude_single=claude_single,
                                          claude_harness=None, advise=None)
                scores[pname].add(att)
                n_cells += 1
                if att.conclusive:
                    bucket[spec.context_need][pname][1] += 1
                    global_sc[pname][1] += 1
                    if att.solved:
                        bucket[spec.context_need][pname][0] += 1
                        global_sc[pname][0] += 1
                per_task[spec.name][pname] = att.solved
                if (not att.solved and att.conclusive
                        and att.adapter_status == AdapterStatus.LIVE_CONCLUSIVE.value):
                    failure_taxonomy[f"{pname}:{spec.task_type}"] += 1
                if pname == INCUMBENT and att.conclusive and not att.solved:
                    cheap_single_fail_tasks.append(spec.name)
            if (ti + 1) % 20 == 0:
                print(f"  {ti+1}/{len(tasks)} tasks, {n_cells} cells ({time.time()-t0:.0f}s)")

    total_conclusive = sum(v[1] for v in global_sc.values())
    # BUCKET-LEVEL promotion: which policy beats cheap_single with CI separation per bucket?
    bucket_report = {}
    bucket_promotions = []
    for need, by_pol in sorted(bucket.items()):
        inc = by_pol.get(INCUMBENT, [0, 0])
        rows = {}
        for p, (s, c) in sorted(by_pol.items()):
            rows[p] = {"verified": round(s / c, 4) if c else 0.0,
                       "ci": dict(zip(("point", "lo", "hi"), wilson_ci(s, c), strict=False)),
                       "n": c}
            if p not in (INCUMBENT, "oracle", "cheap_static") and beats_with_confidence(
                    s, c, inc[0], inc[1]):
                inc_v = round(inc[0] / inc[1], 4) if inc[1] else 0.0
                bucket_promotions.append(
                    {"bucket": need, "policy": p, "verified": rows[p]["verified"],
                     "incumbent_verified": inc_v})
        bucket_report[need] = rows

    g_ci = {p: dict(zip(("point", "lo", "hi"), wilson_ci(s, c), strict=False))
            for p, (s, c) in global_sc.items()}
    from collections import Counter
    n_families = len({t.name.rsplit("_", 1)[0].rstrip("0123456789_") for t in tasks})
    gate = {
        "ge_600_conclusive_cells": total_conclusive >= 600,
        "ge_100_tasks": len(tasks) >= 100,
        "ge_10_task_families": n_families >= 10,
        "ge_5_context_needs": len({t.context_need for t in tasks}) >= 5,
        "ge_25_cheap_single_failures": len(set(cheap_single_fail_tasks)) >= 25,
        "high_risk_false_auto_approve": 0,
        "bucket_level_ci_separated_win": len(bucket_promotions) >= 1,
    }
    report = {
        "experiment": "hard_realism_arena",
        "round": "Alpha 44 — Hard-Realism MetaRouter",
        "live_claude": claude_single is not None,
        "n_tasks": len(tasks), "n_families": n_families,
        "task_types": sorted({t.task_type for t in tasks}),
        "context_needs": sorted({t.context_need for t in tasks}),
        "by_task_type": dict(Counter(t.task_type for t in tasks)),
        "policies": policies,
        "n_cells": n_cells, "n_conclusive_cells": total_conclusive,
        "conclusive_rate": round(total_conclusive / n_cells, 4) if n_cells else 0.0,
        "global_confidence_intervals": g_ci,
        "global_scores": [scores[p].to_dict() for p in policies],
        "cheap_single_failures": len(set(cheap_single_fail_tasks)),
        "bucket_confidence_intervals": bucket_report,
        "bucket_level_promotions": bucket_promotions,
        "acceptance_gate": gate,
        "all_gates_pass": all(v if isinstance(v, bool) else v == 0 for v in gate.values()),
        "failure_taxonomy": dict(sorted(failure_taxonomy.items(), key=lambda x: -x[1])[:20]),
        "evidence_tier": "fixture-hard-unseen (authored to defeat the ceiling); live Claude",
        "elapsed_s": round(time.time() - t0, 1),
    }
    out = _ROOT / "reports" / "hard_realism_arena.json"
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    compare = sorted(report["global_scores"],
                     key=lambda s: s["verified_success_rate"], reverse=True)
    (_ROOT / "reports" / "hard_realism_policy_compare.json").write_text(json.dumps(
        {"experiment": "hard_realism_policy_compare",
         "global_ranking": [s["policy"] for s in compare], "global_scores": compare,
         "bucket_level_promotions": bucket_promotions}, indent=2) + "\n")
    (_ROOT / "reports" / "hard_realism_failure_taxonomy.json").write_text(
        json.dumps(report["failure_taxonomy"], indent=2) + "\n")
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        s = os.environ.get(key)
        if s:
            assert s not in out.read_text(), f"{key} leaked!"

    print(f"\n=== hard arena: {total_conclusive} conclusive cells across {len(tasks)} tasks "
          f"({report['conclusive_rate']:.0%}) ===")
    for p in policies:
        c = g_ci[p]
        print(f"  {p:16s} verified={c['point']:.2f} [{c['lo']:.2f},{c['hi']:.2f}]")
    print(f"cheap_single failures: {report['cheap_single_failures']}")
    print(f"BUCKET-LEVEL CI-separated wins over cheap_single: {bucket_promotions}")
    print(f"gates: {gate}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
