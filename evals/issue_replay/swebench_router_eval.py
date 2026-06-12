# ruff: noqa: E501
"""SWE-bench Lite routing economics (P9) — the de-saturated head-to-head.

Consumes the per-agent solve reports (swebench_solve_{gemini_cli,claude_code,codex_cli}.json) on the
fair slice and computes the meta-router thesis on a DE-SATURATED real benchmark:
  * per-agent solve rate + best single agent (the bar to beat);
  * oracle ensemble (union — any agent solves) = the coverage ceiling;
  * cheapest-first escalation with a verify-stop (gemini -> claude -> codex), oracle-gated as the
    upper bound: solve-rate + agent-invocations + which rung solved + cost (wall-time proxy; vendor
    agents bill $0 metered, so wall-seconds is the honest cost axis here).
The win to demonstrate: escalation matches the union at far fewer strong-agent invocations than
always-using the best single agent — exactly the P3 result, now where the best agent does NOT saturate.

    uv run python -m evals.issue_replay.swebench_router_eval --out reports/swebench_router_eval.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_LADDER = ["gemini_cli", "claude_code", "codex_cli"]   # cheapest-first


def _load(agent: str) -> dict[str, dict]:
    p = Path(f"reports/swebench_solve_{agent}.json")
    if not p.exists():
        return {}
    return {r["instance_id"]: r for r in json.loads(p.read_text()).get("per_task", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/swebench_router_eval.json")
    args = ap.parse_args()
    per_agent = {a: _load(a) for a in _LADDER}
    ids = sorted(set().union(*[set(d) for d in per_agent.values()])) if any(per_agent.values()) else []
    if not ids:
        print("no per-agent solve reports yet — run swebench_solve sweeps first", flush=True)
        return 1

    rows = []
    for iid in ids:
        rec = {"instance_id": iid}
        for a in _LADDER:
            r = per_agent[a].get(iid)
            rec[a] = (bool(r["solved"]) if r else None)
            rec[f"{a}_wall"] = (r.get("wall_s", 0.0) if r else None)
        rows.append(rec)

    n = len(ids)
    per_agent_solved = {a: sum(1 for r in rows if r.get(a)) for a in _LADDER}
    best_single = max(per_agent_solved.items(), key=lambda kv: kv[1])
    union = sum(1 for r in rows if any(r.get(a) for a in _LADDER))

    # cheapest-first escalation, oracle verify-stop (stop at the first rung that actually solves)
    esc_solved = 0
    rung_stops = dict.fromkeys(_LADDER, 0)
    strong_calls = 0          # how often the strongest rung (codex) is invoked
    esc_wall = 0.0
    for r in rows:
        for a in _LADDER:
            esc_wall += r.get(f"{a}_wall") or 0.0
            if a == "codex_cli":
                strong_calls += 1
            if r.get(a):
                esc_solved += 1
                rung_stops[a] += 1
                break

    summary = {
        "n_tasks": n,
        "per_agent_solved": per_agent_solved,
        "per_agent_solve_rate": {a: round(per_agent_solved[a] / n, 3) for a in _LADDER},
        "best_single_agent": {"agent": best_single[0], "solved": best_single[1], "rate": round(best_single[1] / n, 3)},
        "oracle_union_solved": union, "oracle_union_rate": round(union / n, 3),
        "escalation_cheapest_first": {
            "solved": esc_solved, "rate": round(esc_solved / n, 3),
            "stops_by_rung": rung_stops,
            "strong_agent_invocations": strong_calls,
            "strong_agent_invocations_vs_alwaysbest": f"{strong_calls}/{n}",
            "total_wall_s": round(esc_wall, 1),
        },
        "headline": (f"escalation solves {esc_solved}/{n} (= union {union}) using codex on "
                     f"{strong_calls}/{n}; best single agent {best_single[0]} solves {best_single[1]}/{n}"),
        "evidence_tier": "real SWE-bench Lite fair slice; held-out FAIL_TO_PASS grading; vendor agents subscription-metered ($0); wall-time as cost proxy",
    }
    Path(args.out).write_text(json.dumps({**summary, "per_task": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
