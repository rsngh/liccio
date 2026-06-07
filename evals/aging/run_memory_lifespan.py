"""Memory lifespan benchmark (GOALS Alpha 44 P6).

100-session simulated project history with AGING scenarios (AgingBench): the good context
strategy for one failure signature MIGRATES mid-history (repo-convention migration / revision
aging), stale memory must decay unless reconfirmed (maintenance aging), and a poisoned episode
must be quarantined. Measures memory precision over time, post-migration recovery latency, and
memory-on vs memory-off cost per verified success. Deterministic (seeded); no API calls.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.memory import ExperienceBank, ExperienceEpisode, MemoryPolicy  # noqa: E402

N = 100
MIGRATE_AT = 50
_STRATS = ["minimal", "grep", "repo_map"]
_COST = {"minimal": 0.002, "grep": 0.003, "repo_map": 0.004}


def _good(sig: str, t: int) -> str:
    # sig_a's correct strategy migrates from repo_map -> grep at session MIGRATE_AT (revision aging)
    if sig == "sig_a":
        return "repo_map" if t < MIGRATE_AT else "grep"
    return {"sig_b": "grep", "sig_c": "minimal"}[sig]


def _solve(sig: str, strat: str, t: int, rng: random.Random) -> bool:
    return rng.random() < (0.95 if strat == _good(sig, t) else 0.10)


def main() -> int:
    rng = random.Random(11)
    pol = MemoryPolicy(half_life=8.0)     # shorter half-life so stale memory decays after migration
    bank = ExperienceBank()
    sigs = ["sig_a", "sig_b", "sig_c"]
    precision_window: list[int] = []
    timeline = []
    mem_solved = mem_cost = base_solved = base_cost = 0.0
    recovery_session = None
    for t in range(N):
        sig = sigs[t % len(sigs)]
        # memory-off baseline: random strategy
        bp = rng.choice(_STRATS)
        bok = _solve(sig, bp, t, rng)
        base_solved += int(bok)
        base_cost += _COST[bp]
        # memory-on: recommend known-good, avoid known-bad; explore if nothing known
        avoid = bank.avoid_strategies(tenant="acme", failure_signature=sig)
        rec = bank.recommend_strategy(tenant="acme", failure_signature=sig)
        mp = rec or next((s for s in _STRATS if s not in avoid), rng.choice(_STRATS))
        # precision: did the recommendation match the CURRENT ground truth?
        if rec is not None:
            precision_window.append(int(rec == _good(sig, t)))
        mok = _solve(sig, mp, t, rng)
        mem_solved += int(mok)
        mem_cost += _COST[mp]
        bank.write(ExperienceEpisode(
            repo_family="acme", repo_id="r", task_type="bugfix", failure_signature=sig,
            context_strategy=mp, agent="claude", verifier_outcome="solved" if mok else "failed",
            reward=1.0 if mok else -1.0, cost=_COST[mp], privacy_scope="acme",
            created_at=float(t)), policy=pol)
        bank.decay(now=float(t), half_life=pol.half_life)
        # recovery latency: first session after migration where sig_a re-recommends the new good
        if (t >= MIGRATE_AT and recovery_session is None
                and bank.recommend_strategy(tenant="acme", failure_signature="sig_a") == "grep"):
            recovery_session = t - MIGRATE_AT
        timeline.append({"t": t, "sig": sig, "rec": rec, "good": _good(sig, t), "solved": mok})

    # poisoning: inject an internally-inconsistent episode and confirm it's quarantined on write
    poisoned = ExperienceEpisode(repo_family="acme", repo_id="r", task_type="bugfix",
                                 failure_signature="sig_a", context_strategy="minimal",
                                 agent="x", verifier_outcome="solved", reward=-9.0,
                                 privacy_scope="acme", created_at=99.0)
    bank.write(poisoned, policy=pol)
    poisoned_quarantined = any(e.quarantined for e in bank.episodes)

    report = {
        "experiment": "memory_lifespan_benchmark", "n_sessions": N, "migrate_at": MIGRATE_AT,
        "memory_solved": int(mem_solved), "baseline_solved": int(base_solved),
        "memory_cost_per_verified": round(mem_cost / mem_solved, 6) if mem_solved else None,
        "baseline_cost_per_verified": round(base_cost / base_solved, 6) if base_solved else None,
        "memory_reduces_cost_per_success": bool(
            mem_solved and base_solved
            and mem_cost / mem_solved < base_cost / base_solved),
        "recommendation_precision_overall": (
            round(sum(precision_window) / len(precision_window), 4) if precision_window else None),
        "revision_recovery_latency_sessions": recovery_session,
        "revised_after_migration": recovery_session is not None,
        "poisoned_episode_quarantined": poisoned_quarantined,
        "final_recommendations": {s: bank.recommend_strategy(tenant="acme", failure_signature=s)
                                  for s in sigs},
    }
    out = ROOT / "reports" / "memory_lifespan_benchmark.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"memory_solved={int(mem_solved)} vs baseline={int(base_solved)} | "
          f"recovery={recovery_session} | precision={report['recommendation_precision_overall']}")
    print(f"final recs: {report['final_recommendations']} | poisoned={poisoned_quarantined}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
