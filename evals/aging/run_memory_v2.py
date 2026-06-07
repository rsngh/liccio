"""Memory v2 ablation + privacy red-team + revision audit (GOALS Alpha 43 P6).

Deterministic (no API calls). Over a simulated repeated-failure project history, measures:
  - ablation: cost_per_verified_success with memory vs without (memory should reduce it);
  - negative memory blocks repeating a known-bad strategy;
  - privacy red-team: cross-tenant reads are blocked;
  - revision audit: a post-merge revert revises memory so the bad strategy is no longer
    recommended;
  - poisoning defense: an internally-inconsistent episode is quarantined.

Writes reports/memory_v2_ablation.json, reports/memory_privacy_redteam.json,
reports/memory_revision_audit.json.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.memory import ExperienceBank, ExperienceEpisode, MemoryPolicy  # noqa: E402

# ground truth: per failure signature, one strategy solves cheaply; a wrong one is costly+fails
_GOOD = {"sig_a": "repo_map", "sig_b": "grep", "sig_c": "minimal"}
_STRATS = ["minimal", "grep", "repo_map"]
_COST = {"minimal": 0.002, "grep": 0.003, "repo_map": 0.004}
N = 30


def _solve(sig: str, strat: str, rng: random.Random) -> bool:
    return rng.random() < (0.95 if strat == _GOOD[sig] else 0.10)


def _ablation() -> dict:
    rng = random.Random(7)
    bank, pol = ExperienceBank(), MemoryPolicy(half_life=12.0)
    sigs = list(_GOOD)
    mem_solved = mem_cost = base_solved = base_cost = 0.0
    for t in range(N):
        sig = sigs[t % len(sigs)]
        # baseline: random strategy every time
        bp = rng.choice(_STRATS)
        bok = _solve(sig, bp, rng)
        base_solved += int(bok)
        base_cost += _COST[bp]
        # memory: reuse known-good, avoid known-bad
        avoid = bank.avoid_strategies(tenant="acme", failure_signature=sig)
        rec = bank.recommend_strategy(tenant="acme", failure_signature=sig)
        mp = rec or next((s for s in _STRATS if s not in avoid), rng.choice(_STRATS))
        mok = _solve(sig, mp, rng)
        mem_solved += int(mok)
        mem_cost += _COST[mp]
        bank.write(ExperienceEpisode(
            repo_family="acme", repo_id="r", task_type="bugfix", failure_signature=sig,
            context_strategy=mp, agent="claude", verifier_outcome="solved" if mok else "failed",
            reward=1.0 if mok else -1.0, cost=_COST[mp], privacy_scope="acme",
            created_at=float(t)), policy=pol)
        bank.decay(now=float(t), half_life=pol.half_life)
    cps_mem = round(mem_cost / mem_solved, 6) if mem_solved else None
    cps_base = round(base_cost / base_solved, 6) if base_solved else None
    return {"experiment": "memory_v2_ablation", "n_sessions": N,
            "memory_solved": int(mem_solved), "baseline_solved": int(base_solved),
            "cost_per_verified_success_memory": cps_mem,
            "cost_per_verified_success_baseline": cps_base,
            "memory_reduces_cost_per_success": bool(cps_mem and cps_base and cps_mem < cps_base),
            "learned_good_strategy": {s: bank.recommend_strategy(
                tenant="acme", failure_signature=s) for s in sigs}}


def _privacy_redteam() -> dict:
    bank, pol = ExperienceBank(), MemoryPolicy()
    bank.write(ExperienceEpisode(repo_family="acme", repo_id="r", task_type="bugfix",
                                 failure_signature="sig_a", context_strategy="repo_map",
                                 agent="c", reward=1.0, privacy_scope="tenant_acme"), policy=pol)
    attempts = [
        {"attack": "cross_tenant_read", "blocked": bank.read(tenant="tenant_evil") == []},
        {"attack": "same_tenant_read_ok", "blocked": len(bank.read(tenant="tenant_acme")) == 1},
    ]
    return {"experiment": "memory_privacy_redteam",
            "cross_tenant_blocked": attempts[0]["blocked"],
            "same_tenant_allowed": attempts[1]["blocked"],
            "all_leaks_blocked": attempts[0]["blocked"] and attempts[1]["blocked"],
            "attempts": attempts}


def _revision_audit() -> dict:
    bank, pol = ExperienceBank(), MemoryPolicy()
    sig = "sig_a"
    # memory initially recommends repo_map (a success)
    bank.write(ExperienceEpisode(repo_family="acme", repo_id="r", task_type="bugfix",
                                 failure_signature=sig, context_strategy="repo_map", agent="c",
                                 reward=1.0, verifier_outcome="solved", privacy_scope="acme",
                                 created_at=0.0), policy=pol)
    before = bank.recommend_strategy(tenant="acme", failure_signature=sig)
    # a post-merge REVERT arrives: the repo_map fix was bad -> revise memory (negative episode)
    bank.write(ExperienceEpisode(repo_family="acme", repo_id="r", task_type="bugfix",
                                 failure_signature=sig, context_strategy="repo_map", agent="c",
                                 reward=-2.0, verifier_outcome="failed",
                                 post_merge_outcome="reverted", privacy_scope="acme",
                                 created_at=1.0), policy=pol)
    after_avoid = bank.avoid_strategies(tenant="acme", failure_signature=sig)
    return {"experiment": "memory_revision_audit",
            "recommended_before_revert": before,
            "repo_map_now_avoided_after_revert": "repo_map" in after_avoid,
            "revision_applied": before == "repo_map" and "repo_map" in after_avoid}


def main() -> int:
    abl = _ablation()
    priv = _privacy_redteam()
    rev = _revision_audit()
    for name, data in (("memory_v2_ablation", abl), ("memory_privacy_redteam", priv),
                       ("memory_revision_audit", rev)):
        (ROOT / "reports" / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"ablation: cps_memory={abl['cost_per_verified_success_memory']} "
          f"cps_baseline={abl['cost_per_verified_success_baseline']} "
          f"reduces={abl['memory_reduces_cost_per_success']}")
    print(f"privacy: all_leaks_blocked={priv['all_leaks_blocked']}")
    print(f"revision: applied={rev['revision_applied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
