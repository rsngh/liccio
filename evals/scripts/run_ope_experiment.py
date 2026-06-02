"""Alpha 6, WS3 — offline policy evaluation experiment (synthetic, deterministic).

Builds a logged bandit-style dataset under a uniform behavior policy across a few
task types, then evaluates three target policies offline — random, a supervised
meta-router, and greedy-on-reward-model — reporting IPS/SNIPS/clipped-IPS/DR with
bootstrap CIs and overlap diagnostics. Writes ``evals/reports/ope.json``.

No network/key required.
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.routing.ope import OPESample, evaluate_policy, fit_reward_model
from acp.routing.supervised import SupervisedRoutingPolicy

OUT = Path("evals/reports/ope.json")

# Three task types; for each, one agent is the "right" tool. The behavior policy
# logs uniformly over two candidate agents, so a smart target should outperform.
WORLD = {
    "bugfix|medium": {"good": "claude_harness", "bad": "fake"},
    "refactor|low": {"good": "openai_harness", "bad": "patch"},
    "security|high": {"good": "claude_harness", "bad": "openai_harness"},
}


def _key(agent: str, strategy: str = "hybrid_keyword_embedding") -> str:
    # Mirror RoutingAction.key(): kind|name|model|strategy|verif
    return f"harness|{agent}|-|{strategy}|standard"


def _build_log(n_per_ctx: int = 80) -> list[OPESample]:
    samples: list[OPESample] = []
    for ctx, arms in WORLD.items():
        cands = [_key(arms["good"]), _key(arms["bad"])]
        for i in range(n_per_ctx):
            agent = arms["good"] if i % 2 == 0 else arms["bad"]
            reward = 1.0 if agent == arms["good"] else 0.0
            samples.append(OPESample(ctx, _key(agent), behavior_prob=0.5,
                                     reward=reward, candidates=cands))
    return samples


def main() -> int:
    log = _build_log()

    def random_target(ctx, action, cands):
        return 1.0 / len(cands)

    q = fit_reward_model(log)

    def greedy(ctx, action, cands):
        best = max(q(ctx, a) for a in cands)
        winners = [a for a in cands if q(ctx, a) == best]
        return 1.0 / len(winners) if action in winners else 0.0

    sup = SupervisedRoutingPolicy()
    sup.fit([{"context_key": s.context_key, "action_key": s.action_key,
              "reward": s.reward} for s in log])

    targets = {"random": random_target, "greedy": greedy, "supervised": sup.as_target()}
    baseline = sum(s.reward for s in log) / len(log)
    results = {name: evaluate_policy(log, tgt, seed=1).as_dict()
               for name, tgt in targets.items()}

    report = {
        "experiment": "alpha6_offline_policy_evaluation",
        "n": len(log),
        "task_types": list(WORLD.keys()),
        "logged_mean_reward": round(baseline, 6),
        "policies": results,
        "ranking_by_dr": sorted(results, key=lambda k: results[k]["dr"]["value"],
                                reverse=True),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    for name in report["ranking_by_dr"]:
        r = results[name]["dr"]
        print(f"{name:11s} DR={r['value']:.3f} [{r['ci_low']:.3f}, {r['ci_high']:.3f}]")
    print(f"logged_mean={baseline:.3f}; wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
