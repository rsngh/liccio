# ruff: noqa: E501
"""Phase 2 eval — the unified router as a working product that compounds.

Two live demonstrations (Anthropic tiers + the in-process Claude harness; hidden-test verified):

  --mixed        : on a MIXED workload (easy + context-gated), `unified_router` beats every FIXED
                   policy (always-cheap, always-opus, always-harness, fixed-context) on verified
                   success per dollar — it escalates only when the cheap rung fails.
  --longitudinal : the same tasks over N sessions. With MEMORY, the router learns which cheap rungs
                   fail a failure-signature and skips them, so cost-per-verified-success DECLINES
                   over sessions; a MEMORYLESS variant pays the wasted cheap rungs every time (flat).
                   This is value a stateless frontier agent cannot have.

Stop signal: the held-out hidden test (Phase 1 already proved the independent proxy; Phase 2 isolates
the ROUTING composition, so it uses the clean verifier — the production stand-in is the proxy).

    uv run python -m evals.unified_router.run --mixed
    uv run python -m evals.unified_router.run --longitudinal --sessions 5
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from evals.hetero_arena.tiers import HAIKU, OPUS, SONNET
from evals.metarouter_arena.policies import _single_shot
from evals.metarouter_arena.statistics import wilson_ci

from acp.memory.experience_bank import ExperienceBank
from acp.memory.memory_policy import MemoryPolicy
from acp.routing.topology_program_executor import AttemptOutcome
from acp.routing.unified_router import Lever, route_and_solve

# cheapest-first ladder over the proven levers (model tier x context x harness)
LEVERS = [
    Lever("haiku_minimal", est_cost=0.0015, prior_p_solve=0.5),
    Lever("haiku_repomap", est_cost=0.0025, prior_p_solve=0.7),
    Lever("sonnet_repomap", est_cost=0.006, prior_p_solve=0.8),
    Lever("inproc_harness", est_cost=0.02, prior_p_solve=0.85),
    Lever("opus_repomap", est_cost=0.03, prior_p_solve=0.9),
]
_CFG = {
    "haiku_minimal": (HAIKU, "minimal", False),
    "haiku_repomap": (HAIKU, "repo_map", False),
    "sonnet_repomap": (SONNET, "repo_map", False),
    "opus_repomap": (OPUS, "repo_map", False),
}


def _attempt(spec, root, lever_name, *, harness_adapter) -> AttemptOutcome:
    """Run one lever on the task and return the hidden-verified outcome + cost."""
    if lever_name == "inproc_harness":
        from evals.harness_arena.policies import policy_inproc_harness
        att = policy_inproc_harness(spec, root, claude_harness=harness_adapter)
        return AttemptOutcome(solved=att.solved, public_solved=att.public_solved, cost=att.cost_usd)
    tier, ctx, _h = _CFG[lever_name]
    att = _single_shot(tier.adapter(), spec, root, strategy=ctx, policy_name=lever_name,
                       cost_fn=tier.cost)
    return AttemptOutcome(solved=att.solved, public_solved=att.public_solved, cost=att.cost_usd)


def _attempt_fn(spec, root, *, harness_adapter):
    def fn(action: str, _task_id: str):
        if action not in _CFG and action != "inproc_harness":
            return None     # control actions (run_strict_verifier etc.) not applicable here
        return _attempt(spec, root, action, harness_adapter=harness_adapter)
    return fn


def _harness():
    import asyncio

    from acp.agents.claude_harness import ClaudeHarnessAdapter
    h = ClaudeHarnessAdapter(max_steps=8)
    return h if asyncio.run(h.healthcheck()).available else None


def _sig(spec) -> str:
    return f"{spec.task_type}:{spec.context_need}"


def _corpus():
    """Easy (cheap rung solves) + context-gated (needs repo_map) — a mix the router must navigate."""
    from evals.harness_arena.harness_tasks import capability_corpus, ceiling_corpus
    easy = list(capability_corpus())[:4]
    gated = ceiling_corpus(6)
    return easy + gated


def run_mixed() -> dict:
    tasks = _corpus()
    harness = _harness()
    fixed = {"always_cheap": ["haiku_minimal"], "fixed_context": ["haiku_repomap"],
             "always_harness": ["inproc_harness"], "always_opus": ["opus_repomap"]}
    agg = defaultdict(lambda: [0, 0.0])   # policy -> [solved, cost]
    n = 0
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="uniroute_mixed_") as d:
        root = Path(d)
        for spec in tasks:
            n += 1
            afn = _attempt_fn(spec, root, harness_adapter=harness)
            # fixed policies: single fixed lever each
            for name, ladder in fixed.items():
                out = _attempt(spec, root, ladder[0], harness_adapter=harness)
                agg[name][0] += int(out.solved)
                agg[name][1] += out.cost
            # unified router: memoryless here (mixed is about escalation, not compounding)
            res = route_and_solve(task_id=spec.name, failure_signature=_sig(spec),
                                  repo_family="mixed", tenant="t", task_type=spec.task_type,
                                  risk_level=spec.risk_level, budget_class="normal_bugfix",
                                  ladder=LEVERS, attempt_fn=afn, memory=None)
            agg["unified_router"][0] += int(res.solved)
            agg["unified_router"][1] += res.total_cost
            print(f"[mixed {spec.name:18}] unified solved={res.solved} path={res.lever_path} ${res.total_cost:.4f} ({time.time()-t0:.0f}s)", flush=True)

    def row(name):
        s, c = agg[name]
        p, lo, hi = wilson_ci(s, n)
        return {"verified": p, "ci": [lo, hi], "solved": s, "n": n, "total_cost_usd": round(c, 6),
                "cost_per_verified_success": round(c / s, 6) if s else None}
    policies = ["always_cheap", "fixed_context", "always_harness", "always_opus", "unified_router"]
    return {"experiment": "unified_router_mixed", "n_tasks": n,
            "question": "does the unified router beat every fixed policy on verified success per dollar?",
            "results": {p: row(p) for p in policies},
            "elapsed_s": round(time.time() - t0, 1),
            "stop_signal": "held-out hidden test (proxy is the production stand-in)"}


def run_longitudinal(sessions: int) -> dict:
    tasks = _corpus()
    harness = _harness()
    pol = MemoryPolicy()
    mem = ExperienceBank()
    per_session = {"memory": [], "memoryless": []}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="uniroute_long_") as d:
        root = Path(d)
        for s in range(sessions):
            for variant, memory in (("memory", mem), ("memoryless", None)):
                solved = 0
                cost = 0.0
                for spec in tasks:
                    afn = _attempt_fn(spec, root, harness_adapter=harness)
                    res = route_and_solve(task_id=spec.name, failure_signature=_sig(spec),
                                          repo_family="repoX", tenant="t", task_type=spec.task_type,
                                          risk_level=spec.risk_level, budget_class="normal_bugfix",
                                          ladder=LEVERS, attempt_fn=afn,
                                          memory=memory, memory_policy=pol if memory else None,
                                          now=float(s))
                    solved += int(res.solved)
                    cost += res.total_cost
                cps = round(cost / solved, 6) if solved else None
                per_session[variant].append({"session": s, "solved": solved, "n": len(tasks),
                                             "total_cost_usd": round(cost, 6),
                                             "cost_per_verified_success": cps})
            m = per_session["memory"][-1]
            print(f"[session {s}] memory cps={m['cost_per_verified_success']} (solved {m['solved']}/{m['n']}) ({time.time()-t0:.0f}s)", flush=True)

    first = per_session["memory"][0]["cost_per_verified_success"]
    last = per_session["memory"][-1]["cost_per_verified_success"]
    ml_first = per_session["memoryless"][0]["cost_per_verified_success"]
    ml_last = per_session["memoryless"][-1]["cost_per_verified_success"]
    return {"experiment": "unified_router_longitudinal", "sessions": sessions, "n_tasks": len(tasks),
            "question": "does memory make cost-per-verified-success decline over sessions vs a memoryless router?",
            "per_session": per_session,
            "memory_cps_first_vs_last": [first, last],
            "memoryless_cps_first_vs_last": [ml_first, ml_last],
            "memory_compounds": bool(first and last and last < first - 1e-9),
            "memoryless_flat": bool(ml_first and ml_last and abs(ml_last - ml_first) < 1e-6),
            "elapsed_s": round(time.time() - t0, 1),
            "stop_signal": "held-out hidden test"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mixed", action="store_true")
    ap.add_argument("--longitudinal", action="store_true")
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    if args.longitudinal:
        rep = run_longitudinal(args.sessions)
        out = Path(args.out or "reports/unified_router_longitudinal.json")
    else:
        rep = run_mixed()
        out = Path(args.out or "reports/unified_router_eval.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    if args.longitudinal:
        print("\n=== UNIFIED ROUTER — LONGITUDINAL ===")
        for v in ("memory", "memoryless"):
            cps = [s["cost_per_verified_success"] for s in rep["per_session"][v]]
            print(f"{v:11} cost/succ by session: {cps}")
        print(f"memory compounds (cps declines): {rep['memory_compounds']}; memoryless flat: {rep['memoryless_flat']}")
    else:
        print("\n=== UNIFIED ROUTER — MIXED WORKLOAD ===")
        for p, r in rep["results"].items():
            cps = r["cost_per_verified_success"]
            cps_s = f"${cps:.5f}" if cps else "n/a"
            print(f"{p:16} verified {r['verified']:.2f} CI[{r['ci'][0]:.2f},{r['ci'][1]:.2f}] cost/succ {cps_s}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
