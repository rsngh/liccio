# ruff: noqa: E501
"""Increment 2 — memory that survives repo evolution (AgingBench 2605.26302).

Deterministic memory-policy benchmark (like the existing aging benches — no live model noise): one
recurring failure-signature whose *good lever changes over time* (a repo/API migration at session 4,
then a back-migration at session 8). Three routers run the same sessions:

  * memoryless          — always escalates from scratch (stable success, never cheaper);
  * memory (ever-failed)— the current `avoid_strategies` logic: once a lever fails it is avoided
                          forever, so after the back-migration the again-good lever is permanently
                          banned -> the router can no longer solve the task;
  * memory + AGING      — recency/decay-aware avoid+recommend (memory_revision) with a consolidation
                          pass: old failures age out, so the again-good lever is re-used -> recovers.

Headline: aging memory keeps solving across BOTH migrations at low cost; ever-failed memory regresses
(stops solving) after the back-migration. This is the value a stateless agent — and naive memory —
cannot have.

    uv run python -m evals.memory_longitudinal.run --sessions 12
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.memory.experience_bank import ExperienceBank
from acp.memory.memory_policy import MemoryPolicy
from acp.memory.memory_revision import (
    avoid_by_recency,
    consolidate,
    recommend_by_recency,
)
from acp.routing.topology_program_executor import AttemptOutcome
from acp.routing.unified_router import Lever, route_and_solve

LADDER = [Lever("cheap", 0.001, 0.4), Lever("ctx", 0.003, 0.7), Lever("strong", 0.02, 0.9)]
COST = {"cheap": 0.001, "ctx": 0.003, "strong": 0.02}
SIG = "bugfix:evolving"


def _good_lever(session: int) -> str:
    """Ground truth: which lever solves the signature now. Migration at 4, back-migration at 8."""
    if session < 4:
        return "ctx"
    if session < 8:
        return "strong"      # repo/API migration: ctx no longer works, need strong
    return "ctx"             # back-migration: ctx works again


def _attempt_fn(session: int):
    good = _good_lever(session)

    def fn(action, _tid):
        if action not in COST:
            return None
        return AttemptOutcome(solved=(action == good), public_solved=(action == good), cost=COST[action])
    return fn


def _run_variant(variant: str, sessions: int) -> list[dict]:
    bank = ExperienceBank() if variant != "memoryless" else None
    pol = MemoryPolicy() if bank is not None else None
    rec_fn = recommend_by_recency if variant == "memory_aging" else None
    avd_fn = avoid_by_recency if variant == "memory_aging" else None
    out = []
    for s in range(sessions):
        res = route_and_solve(task_id="t", failure_signature=SIG, repo_family="r", tenant="t",
                              task_type="bugfix", risk_level="low", budget_class="normal_bugfix",
                              ladder=LADDER, attempt_fn=_attempt_fn(s), memory=bank,
                              memory_policy=pol, now=float(s),
                              recommend_fn=rec_fn, avoid_fn=avd_fn)
        out.append({"session": s, "solved": res.solved, "cost": round(res.total_cost, 6),
                    "path": res.lever_path})
        if variant == "memory_aging" and bank is not None:
            bank.decay(now=float(s), half_life=2.0)   # age old episodes
            consolidate(bank)                          # sleep-style dedup
    return out


def run(sessions: int) -> dict:
    variants = {v: _run_variant(v, sessions) for v in ("memoryless", "memory", "memory_aging")}

    def post_back(v):  # sessions 8..end: solved count + avg cost (the back-migration recovery window)
        rows = [r for r in variants[v] if r["session"] >= 8]
        solved = sum(int(r["solved"]) for r in rows)
        cost = sum(r["cost"] for r in rows)
        return {"solved": solved, "n": len(rows), "avg_cost": round(cost / len(rows), 6) if rows else None}

    return {
        "experiment": "memory_longitudinal_aging",
        "question": "does aging-aware memory recover after a repo migration AND back, where ever-failed memory gets stuck?",
        "sessions": sessions, "migration_at": 4, "back_migration_at": 8,
        "per_session": variants,
        "post_back_migration": {v: post_back(v) for v in variants},
        "aging_recovers": post_back("memory_aging")["solved"] == post_back("memory_aging")["n"],
        "ever_failed_memory_regresses": post_back("memory")["solved"] < post_back("memory")["n"],
        "evidence_tier": "deterministic memory-policy benchmark (controlled ground-truth migration)",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--out", default="reports/memory_longitudinal.json")
    args = ap.parse_args()
    rep = run(args.sessions)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + "\n")
    print("=== MEMORY AGING (Increment 2) — post-back-migration (sessions 8+) ===")
    for v, r in rep["post_back_migration"].items():
        print(f"  {v:13} solved {r['solved']}/{r['n']}  avg_cost ${r['avg_cost']}")
    print(f"aging recovers: {rep['aging_recovers']}; ever-failed memory regresses: {rep['ever_failed_memory_regresses']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
