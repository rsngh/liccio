"""Bandit Monte Carlo (charter §21.6): N seeds, stationary + drift, vs random."""

from __future__ import annotations

import argparse
import statistics

from acp.routing.simulation import run_simulation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--rounds", type=int, default=1000)
    args = ap.parse_args()

    margins, drift_margins, wins = [], [], 0
    for seed in range(args.seeds):
        r = run_simulation(rounds=args.rounds, seed=seed)
        margins.append(r.policy_reward - r.random_reward)
        wins += int(r.beats_random)
        d = run_simulation(rounds=args.rounds, seed=seed, drift_at=args.rounds // 2)
        drift_margins.append(d.policy_reward - d.random_reward)

    mean = statistics.mean(margins)
    stdev = statistics.pstdev(margins) or 1e-9
    ci = 1.96 * stdev / (len(margins) ** 0.5)
    print(f"seeds={args.seeds} rounds={args.rounds}")
    print(f"bandit beats random in {wins}/{args.seeds} seeds")
    print(f"mean reward margin = {mean:.2f} +/- {ci:.2f} (95% CI)")
    print(f"drift mean margin = {statistics.mean(drift_margins):.2f}")
    assert mean > 0, "bandit did not beat random on average"


if __name__ == "__main__":
    main()
