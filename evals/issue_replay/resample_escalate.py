# ruff: noqa: E501
"""Resample-then-escalate economics (Phase 2) — does resampling the cheap rungs beat blind escalation?

Uses the per-(agent,bundle) multi-sample data from reports/issue_replay_multisample_{agent}_hard.json
(written by multisample.py: each per_bundle has `samples` [0/1] and `samples_to_success`). For each
agent we get best-of-K: solved iff a pass appears within K samples; cost = #samples drawn (verify-stop).

Policies compared on the hard corpus, swept across cost priors (`cost_sensitivity._prior`):
  * blind_escalate           — 1 sample/rung, escalate on fail (today's ladder; = best-of-1).
  * resample_escalate(K)     — up to K verify-stop samples/rung, escalate if best-of-K fails.
Reports per-agent best-of-K solve curves + ladder solve-rate and cost-per-verified-success vs blind,
so we can see where cheap resampling recovers stochastic misses more cost-effectively than escalating.

Honest scope: K is small (whatever each multisample run collected); the per-sample AGREEMENT gate
(stop early on identical failures) needs per-sample signatures not stored here — it's covered by the
router unit tests and the live Phase-4 run, not modeled offline.

    uv run python -m evals.issue_replay.resample_escalate --out reports/issue_replay_resample_escalate.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.issue_replay.cost_sensitivity import ORDER, _prior
from evals.issue_replay.escalation import _load

# agent -> its multisample report (hard corpus); written by multisample.py
MS = {"inproc_repair": "reports/issue_replay_multisample_repair2_hard.json",
      "gemini_cli": "reports/issue_replay_multisample_gemini_hard.json",
      "claude_code": "reports/issue_replay_multisample_claude_hard.json",
      "codex_cli": "reports/issue_replay_multisample_codex_hard.json"}


def _samples_to_success(corpus: str):
    """Per agent: {bundle_idx: s} where s = #samples to first pass (1-based), or None if never.
    Agents without a multisample report fall back to the single-shot solve vector (s=1 or None)."""
    names, solves, _c, _r = _load(corpus)
    n = len(next(iter(solves.values())))
    out: dict[str, dict[int, int | None]] = {}
    maxk: dict[str, int] = {}
    for a in names:
        rep = Path(MS.get(a, ""))
        if rep.exists():
            d = json.loads(rep.read_text())
            recs = {r["idx"]: r for r in d["per_bundle"]}
            maxk[a] = d.get("n_samples", 1)
            out[a] = {i: (recs[i]["samples_to_success"] if i in recs and recs[i].get("solved")
                          else None) for i in range(n)}
            # bundles missing from the (partial) report fall back to single-shot
            for i in range(n):
                if i not in recs:
                    out[a][i] = 1 if solves[a][i] else None
        else:
            maxk[a] = 1
            out[a] = {i: (1 if solves[a][i] else None) for i in range(n)}
    return names, out, maxk, n


def _bestofk_solved(s: int | None, k: int) -> bool:
    return s is not None and s <= k


def _bestofk_cost(s: int | None, k: int) -> int:
    return min(s, k) if (s is not None and s <= k) else k    # samples drawn (verify-stop or all k)


def _ladder_econ(order, sts, k: int, cost: dict[str, float], n: int):
    """resample-escalate with UNIFORM best-of-k per rung; returns (solved, total_cost)."""
    solved = 0
    total = 0.0
    for i in range(n):
        for a in order:
            total += _bestofk_cost(sts[a][i], k) * cost[a]
            if _bestofk_solved(sts[a][i], k):
                solved += 1
                break
    return solved, total


def _ladder_gated(order, sts, k: int, cost: dict[str, float], n: int, *, probe: int = 1):
    """ORACLE-gated resample-escalate (perfect consistency gate, upper bound): at a rung, resample up
    to k ONLY when that (agent,bundle) is actually recoverable within k (stochastic); otherwise pay a
    small `probe` of samples to detect the persistent miss, then escalate. Returns (solved, cost)."""
    solved = 0
    total = 0.0
    for i in range(n):
        for a in order:
            s = sts[a][i]
            if s is not None and s <= k:          # stochastic & recoverable -> resample to the win
                total += s * cost[a]
                solved += 1
                break
            total += probe * cost[a]               # persistent -> gate detects agreement, escalate
    return solved, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="hard", choices=["v1", "hard", "combined"])
    ap.add_argument("--out", default="reports/issue_replay_resample_escalate.json")
    args = ap.parse_args()
    names, sts, maxk, n = _samples_to_success(args.corpus)
    order = [a for a in ORDER if a in names]
    K = max(maxk.values())

    per_agent = {a: {f"best_of_{k}": sum(_bestofk_solved(sts[a][i], k) for i in range(n))
                     for k in range(1, maxk[a] + 1)} for a in order}
    # ladder economics across cost priors
    sweep = []
    for m10 in range(20, 201, 40):
        m = m10 / 10
        cost = _prior(m)
        row = {"expensive_multiplier": m}
        base_solved, base_cost = _ladder_econ(order, sts, 1, cost, n)
        for k in range(1, K + 1):
            sv, ct = _ladder_econ(order, sts, k, cost, n)
            row[f"uniformK{k}"] = {"solved": sv, "cost": round(ct, 3),
                                   "saving_vs_blind": round(1 - (ct / base_cost), 3) if base_cost else 0.0}
        gsv, gct = _ladder_gated(order, sts, K, cost, n)
        row["oracle_gated"] = {"solved": gsv, "cost": round(gct, 3),
                               "cost_per_success": round(gct / gsv, 4) if gsv else None,
                               "saving_vs_blind": round(1 - (gct / base_cost), 3) if base_cost else 0.0}
        sweep.append(row)
    has_resample_data = [a for a in order if maxk[a] > 1]
    rep = {
        "experiment": "issue_replay_resample_escalate", "corpus": args.corpus, "n_bundles": n,
        "ladder": order, "max_k": K,
        "agents_with_multisample_data": has_resample_data,
        "per_agent_best_of_k_solved": per_agent,
        "ladder_economics_sweep": sweep,
        "note": ("best-of-K from real multi-sample data where available, else single-shot fallback. "
                 "K is small (per-run). The agreement-gate refinement is covered by router unit tests + live Phase 4, not modeled here."),
        "evidence_tier": "offline over real per-(agent,bundle) sample vectors; cost priors modeled",
    }
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== RESAMPLE-ESCALATE (corpus={args.corpus}, n={n}, maxK={K}) ===")
    print("agents with real multi-sample data:", has_resample_data)
    for a in order:
        print(f"  {a:14} best-of-k solved: {per_agent[a]}")
    mid = sweep[len(sweep) // 2]
    print(f"ladder @ m={mid['expensive_multiplier']} (vs blind escalation):")
    for k in range(1, K + 1):
        print(f"  uniform best-of-{k}: {mid[f'uniformK{k}']['solved']}/{n}  save {mid[f'uniformK{k}']['saving_vs_blind']}")
    print(f"  ORACLE-gated:       {mid['oracle_gated']['solved']}/{n}  save {mid['oracle_gated']['saving_vs_blind']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
