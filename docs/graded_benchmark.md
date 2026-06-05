# Graded bugfix benchmark (Alpha 23)

The Alpha-22 smoke fixture was a single trivial divide bug — at **ceiling** for a strong
vendor harness, so every live skill canary held at lift 0.0. The graded benchmark replaces
it with a **difficulty-stratified** suite so harness capability and skill lift can be
measured honestly.

## The suite

`src/acp/agents/benchmark_suite.py` — six self-contained bugfix tasks, each a git repo
whose tests fail until the bug is fixed:

| difficulty | tasks |
|------------|-------|
| easy   | `divide`, `factorial` |
| medium | `slugify`, `chunk` |
| hard   | `roman` (subtractive numerals), `merge_intervals` |

Every task ships a **reference fix**, and `tests/unit/test_benchmark_suite.py` proves —
with no vendor call — that each task FAILS on its buggy module and PASSES the reference
fix. So a harness that fails a task failed a genuinely-solvable one, and a passing harness
solved a genuinely-broken one.

## Running it

```bash
# capability by difficulty, no skill (skips unavailable harnesses)
uv run acp eval benchmark-baseline --harness claude_code --reps 1

# live baseline artifact
uv run python evals/scripts/run_benchmark_baseline_live.py   # -> reports/live/benchmark_baseline.json

# skill lift A/B (baseline vs verify-and-edge-cases skill), z-test + Bayesian
uv run python evals/scripts/run_benchmark_skill_ab_live.py   # -> reports/live/benchmark_skill_ab.json
```

`run_benchmark` (in `src/acp/evaluation/benchmark_runner.py`) aggregates solve rate
**overall and per difficulty** through the measurement-hygiene layer: only conclusive
attempts count, and timeouts are infra/inconclusive — never capability failures.

## Live baseline (claude_code)

Real headroom — the harness is **not** at ceiling:

```
overall = 0.667   easy 1.0   medium 0.5   hard 0.5
```

This is the first live task where a skill can show measurable lift. The governance loop
promotes a skill only if it lifts a tier with headroom (lift > 0 with sufficient
P(better)); otherwise it holds — honestly.
