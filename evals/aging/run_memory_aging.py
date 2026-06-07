"""Memory aging smoke (GOALS Alpha 42 P10).

Simulates a 30-session project history over a few recurring failure signatures and measures
whether the experience bank improves FIRST-ATTEMPT success vs a memoryless baseline, that
negative memory steers away from known-bad strategies, and that old memory decays. Deterministic
(seeded) — no API calls. Writes reports/memory_aging_smoke.json.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.memory import ExperienceBank, ExperienceEpisode, MemoryPolicy  # noqa: E402

# Ground truth: for each failure signature, exactly one context strategy reliably solves it.
_GOOD = {"AssertionError:median": "repo_map", "ImportError:helper": "grep",
         "Timeout:io": "minimal"}
_STRATS = ["minimal", "grep", "repo_map"]
N_SESSIONS = 30


def _solves(failure_signature: str, strategy: str, rng: random.Random) -> bool:
    # the right strategy solves ~95% of the time; a wrong one ~10% (noise).
    p = 0.95 if strategy == _GOOD[failure_signature] else 0.10
    return rng.random() < p


def main() -> int:
    rng = random.Random(1234)
    pol = MemoryPolicy(half_life=12.0)
    bank = ExperienceBank()
    sigs = list(_GOOD)
    mem_first_try, base_first_try = 0, 0
    timeline = []
    for t in range(N_SESSIONS):
        sig = sigs[t % len(sigs)]
        # --- memoryless baseline: pick a strategy at random ---
        base_pick = rng.choice(_STRATS)
        base_ok = _solves(sig, base_pick, rng)
        base_first_try += int(base_ok)
        # --- memory router: reuse a known-good strategy, avoid known-bad ---
        rec = bank.recommend_strategy(tenant="acme", failure_signature=sig)
        avoid = bank.avoid_strategies(tenant="acme", failure_signature=sig)
        mem_pick = rec or next((s for s in _STRATS if s not in avoid), rng.choice(_STRATS))
        mem_ok = _solves(sig, mem_pick, rng)
        mem_first_try += int(mem_ok)
        # write the conclusive outcome to memory (negative failures included)
        bank.write(ExperienceEpisode(
            repo_family="acme/app", task_type="bugfix", failure_signature=sig,
            context_strategy=mem_pick, agent="claude_harness",
            verifier_outcome="solved" if mem_ok else "failed",
            reward=1.0 if mem_ok else -1.0, privacy_scope="acme", created_at=float(t)),
            policy=pol)
        bank.decay(now=float(t), half_life=pol.half_life)
        timeline.append({"session": t, "sig": sig, "mem_pick": mem_pick, "mem_ok": mem_ok,
                         "base_pick": base_pick, "base_ok": base_ok})

    mem_rate = round(mem_first_try / N_SESSIONS, 4)
    base_rate = round(base_first_try / N_SESSIONS, 4)
    # by the second half, memory should have learned the good strategy for each signature
    second_half = [r for r in timeline if r["session"] >= N_SESSIONS // 2]
    mem_late = round(sum(r["mem_ok"] for r in second_half) / len(second_half), 4)
    report = {
        "experiment": "memory_aging_smoke",
        "n_sessions": N_SESSIONS,
        "failure_signatures": sigs,
        "memory_first_attempt_success": mem_rate,
        "baseline_first_attempt_success": base_rate,
        "memory_lift": round(mem_rate - base_rate, 4),
        "memory_late_phase_success": mem_late,
        "memory_helps": mem_rate > base_rate,
        "learned_good_strategy_per_signature": {
            s: bank.recommend_strategy(tenant="acme", failure_signature=s) for s in sigs},
        "decay_min": round(min(e.decay_score for e in bank.episodes), 6),
        "note": "deterministic simulation; live repeated-failure-family proof is future work",
    }
    out = ROOT / "reports" / "memory_aging_smoke.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"memory first-attempt={mem_rate} baseline={base_rate} lift={report['memory_lift']} "
          f"late_phase={mem_late}")
    print(f"learned: {report['learned_good_strategy_per_signature']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
