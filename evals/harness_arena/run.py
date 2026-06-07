# ruff: noqa: E501
"""Harness Arena runner — route across AGENT HARNESSES (not just LLM models).

Sweeps {single_shot, inproc_harness, gemini_cli, openhands} over a corpus and grades every attempt
with the SAME held-out hidden test. Reports verified success (Wilson CI), public success, latency,
cost where attributable, and harness signals — separating availability from capability.

    uv run python -m evals.harness_arena.run --corpus capability --trials 1
    uv run python -m evals.harness_arena.run --corpus ceiling --trials 1
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from evals.harness_arena.harness_tasks import corpus
from evals.harness_arena.policies import ALL_POLICIES
from evals.metarouter_arena.schema import PolicyScore
from evals.metarouter_arena.statistics import beats_with_confidence, wilson_ci

DEFAULT = ["single_shot", "inproc_harness", "gemini_cli", "openhands"]
CONTROL = "single_shot"


def _adapters():
    single = harness = None
    gkey = os.environ.get("GEMINI_API_KEY")
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
        import asyncio

        from acp.agents.claude_agent import ClaudeAgentAdapter
        from acp.agents.claude_harness import ClaudeHarnessAdapter
        s = ClaudeAgentAdapter(model="claude-sonnet-4-6")
        single = s if asyncio.run(s.healthcheck()).available else None
        h = ClaudeHarnessAdapter(max_steps=8)
        harness = h if asyncio.run(h.healthcheck()).available else None
    return single, harness, gkey


def _ci(s, n):
    return dict(zip(("point", "lo", "hi"), wilson_ci(s, n), strict=False))


def run(corpus_name: str, trials: int, policies: list[str]) -> dict:
    tasks = corpus(corpus_name)
    single, harness, gkey = _adapters()
    kw = {"claude_single": single, "claude_harness": harness, "gemini_key": gkey}
    scores = {p: PolicyScore(policy=p) for p in policies}
    glob = defaultdict(lambda: [0, 0])
    per_task = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    n_cells = 0
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="harness_arena_") as d:
        root = Path(d)
        for trial in range(trials):
            for spec in tasks:
                for pname in policies:
                    att = ALL_POLICIES[pname](spec, root, **kw)
                    scores[pname].add(att)
                    n_cells += 1
                    if att.conclusive:
                        glob[pname][1] += 1
                        per_task[spec.name][pname][1] += 1
                        if att.solved:
                            glob[pname][0] += 1
                            per_task[spec.name][pname][0] += 1
                    print(f"[{corpus_name} t{trial}] {spec.name:22} {pname:16} "
                          f"solved={att.solved} conc={att.conclusive} {att.latency_s}s "
                          f"${att.cost_usd:.4f} {att.detail[:40]}", flush=True)

    summaries = {p: scores[p].to_dict() for p in policies}
    rows = {}
    for p in policies:
        s, c = glob[p]
        sd = summaries[p]
        rows[p] = {"verified": sd["verified_success_rate"], "ci": _ci(s, c), "n_conclusive": c,
                   "public_pass_rate": sd["public_pass_rate"],
                   "unavailable_rate": sd["adapter_unavailable_rate"],
                   "total_cost_usd": sd["total_cost_usd"],
                   "cost_per_verified_success": sd["cost_per_verified_success"],
                   "avg_latency_s": sd["avg_latency_s"],
                   "beats_single_shot_with_ci": (p != CONTROL and beats_with_confidence(s, c, *glob[CONTROL]))}
    return {
        "experiment": "harness_arena",
        "corpus": corpus_name,
        "question": ("does autonomous harness scaffolding rescue context-gated tasks a single model call fails?"
                     if corpus_name == "ceiling"
                     else "is a harness overkill when the task is already well-specified?"),
        "harnesses": {
            "single_shot": "claude-sonnet-4-6, one API call, minimal context (no harness)",
            "inproc_harness": "claude-sonnet-4-6, ACP in-process tool loop",
            "gemini_cli": "gemini-2.5-flash via Google's `gemini` CLI agent (sandboxed)",
            "openhands": "gemini-2.5-flash via OpenHands V1 local-runtime agent (sandboxed, no Docker)",
        },
        "claude_code_cli_status": "installed (v2.1.168) but UNRUNNABLE here: binary behind a read-only 700 root mount; non-root can't reach it and the CLI refuses --dangerously-skip-permissions as root. Represented by inproc_harness.",
        "trials": trials, "n_tasks": len(tasks), "policies": policies,
        "n_cells": n_cells, "elapsed_s": round(time.time() - t0, 1),
        "results": rows,
        "per_task": {t: {p: {"verified": round(v[0] / v[1], 4) if v[1] else 0.0, "n": v[1]}
                         for p, v in by.items()} for t, by in per_task.items()},
        "evidence_tier": "live agent harnesses (Anthropic + Google), hidden-test verified, Wilson CIs",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="capability", choices=["capability", "ceiling"])
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--policies", default=",".join(DEFAULT))
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    rep = run(args.corpus, args.trials, args.policies.split(","))
    out = Path(args.out or f"reports/harness_arena_{args.corpus}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    print(f"\n=== HARNESS ARENA ({args.corpus}) ===")
    for p in args.policies.split(","):
        r = rep["results"][p]
        cps = r["cost_per_verified_success"]
        cps_s = f"${cps:.4f}" if cps is not None else "  n/a "
        print(f"{p:16} verified {r['verified']:.2f} CI[{r['ci']['lo']:.2f},{r['ci']['hi']:.2f}] "
              f"public {r['public_pass_rate']:.2f} cost/succ {cps_s} {r['avg_latency_s']:.0f}s "
              f"{'BEATS single_shot' if r['beats_single_shot_with_ci'] else ''}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
