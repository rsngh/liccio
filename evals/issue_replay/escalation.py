# ruff: noqa: E501
"""ACP routing vs agent-only — cost economics from the real per-agent results (GOALS P3).

P1 measured each agent alone on the 17 real bundles. This is the offline policy evaluation that
quantifies the meta-router's value: a cheapest-first escalation ladder with verify-stop (run the
cheap agent, check the repo's tests pass, escalate ONLY on failure) reaches the pool's union solve
rate while barely touching the expensive agents — vs "agent-only" which runs one (often the
strongest) agent on every task.

Faithful by construction: an agent "succeeds" on a bundle iff its produced module passed the
held-out test (the real acceptance check the router would run as its stop-signal). Invocation
counts are exact from the per-agent solve vectors; the per-agent dollar figure is a transparent
effective-cost prior (subscriptions bill $0 metered, so we model all agents at API-equivalent
rates for a fair comparison — stated, not measured).

    uv run python -m evals.issue_replay.escalation --out reports/issue_replay_routing_economics.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# (report path, effective-cost prior per successful-or-attempted run, in illustrative $ units).
# Ordered cheapest -> strongest; the prior models API-equivalent compute (subscription = $0 metered,
# but modeled here so the routing economics are meaningful and scale-relevant).
AGENTS = [
    ("inproc_repair", "reports/issue_replay_repair_real_gemini.json", 0.02),
    ("gemini_cli", "reports/issue_replay_vendor_gemini_cli_real.json", 0.06),
    ("claude_code", "reports/issue_replay_vendor_claude_code_real.json", 0.10),
    ("codex_cli", "reports/issue_replay_vendor_codex_cli_real.json", 0.12),
]


def _load() -> tuple[list[str], dict[str, list[int]], dict[str, float], list[str]]:
    names, solves, cost, repos = [], {}, {}, []
    for name, path, c in AGENTS:
        if not Path(path).exists():
            continue
        d = json.loads(Path(path).read_text())
        pb = d["per_bundle"]
        names.append(name)
        solves[name] = [int(r["hidden_pass"]) for r in pb]
        cost[name] = c
        if not repos:
            repos = [r["repo"] for r in pb]
    return names, solves, cost, repos


def _agent_only(name: str, solves: dict, cost: dict, n: int) -> dict:
    s = sum(solves[name])
    total = n * cost[name]
    return {"policy": f"agent_only:{name}", "solved": s, "n": n,
            "invocations": {name: n}, "strongest_invocations": n if name == "codex_cli" else 0,
            "effective_cost": round(total, 4),
            "cost_per_success": round(total / s, 4) if s else None}


def _escalation(order: list[str], solves: dict, cost: dict, n: int) -> dict:
    """Cheapest-first; for each bundle try rungs in order, stop at the first that solves (verify)."""
    solved = 0
    inv = dict.fromkeys(order, 0)
    total = 0.0
    stop_rung = dict.fromkeys([*order, "unsolved"], 0)
    for i in range(n):
        done = False
        for a in order:
            inv[a] += 1
            total += cost[a]
            if solves[a][i]:
                solved += 1
                stop_rung[a] += 1
                done = True
                break
        if not done:
            stop_rung["unsolved"] += 1
    return {"policy": "acp_escalation(cheapest-first, verify-stop)", "solved": solved, "n": n,
            "invocations": inv, "strongest_invocations": inv.get("codex_cli", 0),
            "stop_rung": stop_rung, "effective_cost": round(total, 4),
            "cost_per_success": round(total / solved, 4) if solved else None}


def _ensemble(order: list[str], solves: dict, cost: dict, n: int) -> dict:
    """Best-of-pool: run all agents, verifier selects any that solves (boosting upper bound)."""
    solved = sum(1 for i in range(n) if any(solves[a][i] for a in order))
    total = n * sum(cost[a] for a in order)
    return {"policy": "acp_ensemble(all+verify-select)", "solved": solved, "n": n,
            "invocations": dict.fromkeys(order, n), "strongest_invocations": n,
            "effective_cost": round(total, 4),
            "cost_per_success": round(total / solved, 4) if solved else None}


def _family_memory(order: list[str], solves: dict, cost: dict, repos: list[str]) -> dict:
    """Per-family memory: for each repo family, default to the cheapest agent that solved any of its
    bundles; if it misses a bundle, escalate. Models 'learn the cheap lever per family'."""
    fams: dict[str, list[int]] = {}
    for i, r in enumerate(repos):
        fams.setdefault(r, []).append(i)
    solved = 0
    total = 0.0
    chosen: dict[str, str] = {}
    for fam, idxs in fams.items():
        best = next((a for a in order if any(solves[a][i] for i in idxs)), order[-1])
        chosen[fam] = best
        for i in idxs:
            # try the family-default first, then escalate up the ladder on miss
            for a in order[order.index(best):]:
                total += cost[a]
                if solves[a][i]:
                    solved += 1
                    break
    return {"policy": "acp_family_memory", "solved": solved, "n": len(repos),
            "family_default": chosen, "effective_cost": round(total, 4),
            "cost_per_success": round(total / solved, 4) if solved else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/issue_replay_routing_economics.json")
    args = ap.parse_args()
    names, solves, cost, repos = _load()
    n = len(next(iter(solves.values())))
    order = [a for a in ("inproc_repair", "gemini_cli", "claude_code", "codex_cli") if a in names]
    policies = [_agent_only(a, solves, cost, n) for a in names]
    policies.append(_escalation(order, solves, cost, n))
    policies.append(_ensemble(order, solves, cost, n))
    fam = _family_memory(order, solves, cost, repos)
    rep = {
        "experiment": "issue_replay_routing_economics",
        "question": "does ACP routing match the best single agent's solve rate at lower cost than running it on every task?",
        "n_bundles": n, "ladder_cheapest_first": order,
        "effective_cost_prior_usd": {a: c for a, c in [(x[0], x[2]) for x in AGENTS] if a in names},
        "note": "subscriptions bill $0 metered; effective-cost prior models API-equivalent compute for a fair, scale-relevant comparison. Solve/invocation counts are exact from the real per-agent results.",
        "policies": policies, "family_memory": fam,
    }
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== ACP ROUTING vs AGENT-ONLY (n={n}, cheapest-first ladder {order}) ===")
    print(f"{'policy':46} {'solved':>7} {'strongest_runs':>15} {'eff_cost':>9} {'cost/succ':>10}")
    for p in policies:
        print(f"{p['policy']:46} {str(p['solved'])+'/'+str(n):>7} {p.get('strongest_invocations',0):>15} "
              f"{p['effective_cost']:>9} {str(p['cost_per_success']):>10}")
    esc = next(p for p in policies if p["policy"].startswith("acp_escalation"))
    print("escalation stop-rung:", esc["stop_rung"])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
