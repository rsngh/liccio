# Round 26 — Productionization, Real-World Evidence & AgensFlow Coordination

Executing the round-26 plan: deepen real-world evidence + make coordination an explicit,
auditable policy. Live testing throughout.

## Alpha 33 — coordination policy graph v2 (AgensFlow)

`policy_graph` makes the learned artifact an auditable policy, not a fixed pipeline:
- **FoldedTaskSignature** folds (regime, risk, ambiguity, evidence, reliability, measurement)
  into a compact key so similar situations share evidence.
- **PolicyGraph** learns signature→action value from CONCLUSIVE rewards only (the
  measurement-trust invariant), with a global fallback for unseen signatures and
  **warm-start** transfer across repos/families at a discount.
- **skip_policy** decides skip:planner/retrieval by signature but NEVER skips strict verify on
  high-risk/untrusted.
- **reward_audit** lets a cross-judge check block a promotion.

Imports AgensFlow's folded signatures, skip topology, warm-start transfer, and reward audit.

## Alpha 29 — real-world bug shapes (escape synthetic)

`repo_replay` adds 5 realistic bug shapes (semver string-compare, 1-indexed pagination
off-by-one, shallow config deep_merge, LRU recency, path normalization) with an ISSUE
description + hidden tests, proven solvable offline. **Honest evidence tier = fixture**
(real-world-SHAPED, not scraped real_repo_replay history — that needs a GitHub ingestor +
network/auth absent here).

### The sharpest non-ceiling finding yet (live)

`run_repo_replay_live` (gpt-4o-mini, blind + hidden tests): single-shot **0.6**, best-of-5
**0.6**, lift **0.0**. semver/deep_merge/normalize_path solve 5/5; **paginate and lru_cache
fail 0/5 AND best-of-5 also fails**. Insight: best-of-k rescues **variance** (model sometimes
right), not **systematic** capability gaps (model always writes the wrong logic).

### The complete compute-policy picture (live)

`run_repo_replay_advisor_live` on the systematically-failing tasks:

| arm | solve rate |
|---|---|
| executor_only (gpt-4o-mini) | 0.0 |
| best-of-k | 0.0 |
| **executor + advisor** (gpt-4o diagnosis → cheap retry) | **0.5** |
| frontier_single (gpt-4o) | 0.5 |

This proves the compute policy end-to-end: **best-of-k for variance, advisor/frontier for
systematic gaps** — frontier compute earns its keep exactly where cheap sampling cannot.

## Net

The coordination layer is now an explicit, warm-startable AgensFlow policy; evidence moved
from arithmetic toward real-world bug shapes; and the compute-escalation policy is
live-proven across the full spectrum (ceiling → variance → systematic). Every report carries
an honest evidence tier.

## Gate

```
uv run pytest -q --timeout=300
uv run ruff check . && uv run mypy src
uv run acp reports validate
uv run python evals/scripts/run_repo_replay_live.py
uv run python evals/scripts/run_repo_replay_advisor_live.py
```
