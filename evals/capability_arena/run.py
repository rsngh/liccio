# ruff: noqa: E501
"""Capability arena — does a verifier-gated ensemble of CHEAP diverse agents match a STRONG single
agent by capturing the union of their attempts? (Boosting Weak Reasoning Models 2605.14163.)

For each hard task: run diverse cheap arms (gemini-flash-lite, haiku, gemini-flash) — uncorrelated
failures — generate independent tests, proxy-verify with cross-agent consensus, and let the
capability_router select (spend-to-budget). Compare:

  * each SINGLE arm's verified rate (the best is "best single cheap agent"),
  * a STRONG single agent (opus + repo_map) — the frontier reference,
  * the ENSEMBLE (verifier-gated union),

and report the **any-correct oracle ceiling** + **verifier capture rate** + **proxy precision/recall**
(the gating number — capability gain is capped by it). Honest: if the best single arm already solves
everything, there is no headroom and we say so (needs harder / real tasks — the stated dependency).

    uv run python -m evals.capability_arena.run --tasks 10
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from evals.hetero_arena.tier_tasks import all_capability_tasks
from evals.hetero_arena.tiers import GEMINI_FLASH, GEMINI_FLASH_LITE, HAIKU, OPUS
from evals.independent_proof.run import _anthropic_client, _make_candidate
from evals.metarouter_arena.statistics import wilson_ci

from acp.routing.capability_router import Candidate, oracle_capture_rate, solve_ensemble
from acp.verification.independent_proof import generate_checks, proxy_evaluate

ARMS = [GEMINI_FLASH_LITE, HAIKU, GEMINI_FLASH]   # cheap, diverse (cross-provider), cheapest-first
STRONG = OPUS


def _ci(s, n):
    p, lo, hi = wilson_ci(s, n)
    return {"rate": p, "ci": [lo, hi], "solved": s, "n": n}


def run(n_tasks: int) -> dict:
    tasks = sorted(all_capability_tasks(),
                   key=lambda t: {"easy": 2, "medium": 1, "hard": 0}.get(t.difficulty_band, 0))[:n_tasks]
    client = _anthropic_client()
    arm_solved = {t.name: 0 for t in ARMS}
    strong_solved = 0
    ens_results = []
    ens_cost = strong_cost = 0.0
    tp = fp = fn = tn = 0
    n = 0
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="capability_") as d:
        root = Path(d)
        for spec in tasks:
            # run the diverse cheap arms (one candidate each)
            cands = {}
            for i, tier in enumerate(ARMS):
                c = _make_candidate(tier, spec, root, i)
                if c:
                    cands[tier.name] = c
            if len(cands) < 2:
                continue
            n += 1
            # strong single-agent reference (opus + repo_map)
            sc = _make_candidate(STRONG, spec, root, 99)
            if sc:
                strong_solved += int(sc["hidden_pass"])
                strong_cost += sc["cost"]
            # generate independent checks + proxy-verify all arm candidates (cross-agent consensus)
            gen = generate_checks(spec, client=client, n=6)
            verdicts = proxy_evaluate(spec, [{"id": k, "workspace": c["workspace"],
                                              "public_pass": c["public_pass"], "diff": c["diff"]}
                                             for k, c in cands.items()], root, checks=gen.checks)
            # proxy precision/recall vs hidden truth (the gating number)
            for k, c in cands.items():
                pred, truth = verdicts[k].proxy_pass, c["hidden_pass"]
                tp += int(pred and truth)
                fp += int(pred and not truth)
                fn += int(not pred and truth)
                tn += int(not pred and not truth)
                arm_solved[k] += int(c["hidden_pass"])
            # ensemble via the capability router (cheapest-first, spend-to-budget)
            ens_cands = {k: Candidate(arm=k, public_pass=c["public_pass"], hidden_pass=c["hidden_pass"],
                                      cost=c["cost"], workspace=c["workspace"], diff=c["diff"])
                         for k, c in cands.items()}
            order = [t.name for t in ARMS if t.name in ens_cands]
            r = solve_ensemble(arms=order, run_arm_fn=lambda a, _c=ens_cands: _c[a],
                               verify_fn=lambda ran, _v=verdicts: {c.arm: _v[c.arm].proxy_pass for c in ran},
                               budget=0.30)
            ens_results.append(r)
            ens_cost += r.total_cost + gen.cost_usd
            print(f"[{spec.name:18}] ensemble={r.solved} any_correct={r.any_correct} sel={r.selected_arm} "
                  f"opus={sc['hidden_pass'] if sc else '?'} ({time.time()-t0:.0f}s)", flush=True)

    ens_solved = sum(int(r.solved) for r in ens_results)
    best_arm = max(arm_solved, key=lambda k: arm_solved[k]) if arm_solved else None
    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None
    return {
        "experiment": "capability_arena",
        "question": "does a verifier-gated ensemble of cheap diverse agents match a strong single agent by capturing the union?",
        "arms": [t.name for t in ARMS], "strong_reference": STRONG.name, "n_tasks": n,
        "ensemble": {**_ci(ens_solved, n), "total_cost_usd": round(ens_cost, 6),
                     "cost_per_verified_success": round(ens_cost / ens_solved, 6) if ens_solved else None},
        "single_arms": {k: _ci(v, n) for k, v in arm_solved.items()},
        "best_single_cheap_arm": {"arm": best_arm, **_ci(arm_solved.get(best_arm, 0), n)} if best_arm else None,
        "strong_single": {**_ci(strong_solved, n), "total_cost_usd": round(strong_cost, 6),
                          "cost_per_verified_success": round(strong_cost / strong_solved, 6) if strong_solved else None},
        "oracle_capture": oracle_capture_rate(ens_results),
        "proxy_precision_recall": {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn},
        "elapsed_s": round(time.time() - t0, 1),
        "honest_note": "cheap-diverse-arm ensemble demonstrating the mechanism (2605.14163). If the best single arm already solves all tasks, headroom is 0 and the capability gain needs harder / real tasks (network-blocked here).",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=10)
    ap.add_argument("--out", default="reports/capability_arena.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    rep = run(args.tasks)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    e, s = rep["ensemble"], rep["strong_single"]
    b = rep["best_single_cheap_arm"]
    print("\n=== CAPABILITY ARENA ===")
    print(f"ensemble (cheap diverse) : {e['rate']:.2f} CI[{e['ci'][0]:.2f},{e['ci'][1]:.2f}] cost/succ ${e['cost_per_verified_success']}")
    print(f"best single cheap arm    : {b['arm']} {b['rate']:.2f} CI[{b['ci'][0]:.2f},{b['ci'][1]:.2f}]")
    print(f"strong single (opus)     : {s['rate']:.2f} CI[{s['ci'][0]:.2f},{s['ci'][1]:.2f}] cost/succ ${s['cost_per_verified_success']}")
    print(f"oracle capture           : {rep['oracle_capture']}")
    print(f"proxy precision/recall   : {rep['proxy_precision_recall']['precision']}/{rep['proxy_precision_recall']['recall']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
