# ruff: noqa: E501
"""Increment 3 — self-tuning ladder learned offline from traces (AutoTTS 2605.08083).

Three task families need different levers (sigA→cheap, sigB→ctx, sigC→strong). We log training
traces, learn a per-signature ladder offline, then evaluate it against the hand-tuned global ladder
on HELD-OUT tasks. Both should verify 100%; the learned ladder starts at the historically-best rung
and so avoids the escalation warm-up — lower cost per verified success. Deterministic (it tests the
LADDER policy; live model noise is isolated in the other arenas).

    uv run python -m evals.learned_ladder.run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.routing.learned_ladder import Trace, learn_ladder
from acp.routing.topology_program_executor import AttemptOutcome
from acp.routing.unified_router import Lever, route_and_solve

COST = {"cheap": 0.001, "ctx": 0.004, "strong": 0.02}
GLOBAL_ORDER = ["cheap", "ctx", "strong"]
GLOBAL_LEVERS = [Lever("cheap", 0.001, 0.5), Lever("ctx", 0.004, 0.75), Lever("strong", 0.02, 0.9)]
GOOD = {"sigA": "cheap", "sigB": "ctx", "sigC": "strong"}   # ground truth per family


def _attempt_fn(sig):
    good = GOOD[sig]

    def fn(action, _tid):
        if action not in COST:
            return None
        return AttemptOutcome(solved=(action == good), public_solved=(action == good), cost=COST[action])
    return fn


def _collect_training_traces() -> list[Trace]:
    # logged history: every lever tried on every family (full coverage), repeated a few times
    traces = []
    for sig, good in GOOD.items():
        for _ in range(3):
            for lever in GLOBAL_ORDER:
                traces.append(Trace(sig, lever, solved=(lever == good), cost=COST[lever]))
    return traces


def _eval_router(ladder_for, held_out) -> dict:
    solved = 0
    cost = 0.0
    for sig in held_out:
        ladder = [lev for lev in GLOBAL_LEVERS if lev.name in ladder_for(sig)] or GLOBAL_LEVERS
        # preserve the learned order
        order = ladder_for(sig)
        ladder = sorted(ladder, key=lambda lev: order.index(lev.name) if lev.name in order else 99)
        res = route_and_solve(task_id="t", failure_signature=sig, repo_family="r", tenant="t",
                              task_type="bugfix", risk_level="low", budget_class="normal_bugfix",
                              ladder=ladder, attempt_fn=_attempt_fn(sig), memory=None)
        solved += int(res.solved)
        cost += res.total_cost
    n = len(held_out)
    return {"solved": solved, "n": n, "total_cost_usd": round(cost, 6),
            "cost_per_verified_success": round(cost / solved, 6) if solved else None}


def run() -> dict:
    learned = learn_ladder(_collect_training_traces(), fallback_order=GLOBAL_ORDER)
    held_out = ["sigA", "sigB", "sigC"] * 4   # new tasks of known families
    global_res = _eval_router(lambda _sig: GLOBAL_ORDER, held_out)
    learned_res = _eval_router(learned.ladder_for, held_out)
    return {
        "experiment": "learned_ladder",
        "question": "does an offline-learned per-signature ladder beat hand-tuned global escalation per dollar?",
        "learned_ladders": learned.per_signature,
        "global": global_res, "learned": learned_res,
        "both_solve_all": global_res["solved"] == global_res["n"] == learned_res["solved"] == learned_res["n"],
        "learned_cheaper": (learned_res["cost_per_verified_success"] or 9) < (global_res["cost_per_verified_success"] or 9),
        "cost_reduction_pct": round(100 * (1 - (learned_res["cost_per_verified_success"] or 0) / (global_res["cost_per_verified_success"] or 1)), 1),
        "evidence_tier": "deterministic ladder-policy benchmark (offline-learned vs hand-tuned)",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/learned_ladder_eval.json")
    args = ap.parse_args()
    rep = run()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + "\n")
    print("=== LEARNED LADDER (Increment 3) ===")
    print("learned ladders:", rep["learned_ladders"])
    print(f"global  : {rep['global']['solved']}/{rep['global']['n']} @ ${rep['global']['cost_per_verified_success']}/success")
    print(f"learned : {rep['learned']['solved']}/{rep['learned']['n']} @ ${rep['learned']['cost_per_verified_success']}/success")
    print(f"both solve all: {rep['both_solve_all']}; learned cheaper by {rep['cost_reduction_pct']}%")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
