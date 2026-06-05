# Alpha 23 — Graded Live Benchmark & Honest Skill-Lift Checklist

Status: COMPLETE. The governance loop both **holds** (no fabricated lift) and **promotes**
(first live skill deployed on real, guardrail-clean evidence). See `ALPHA23_REPORT.md`.

## Workstreams

- [x] WS1 — graded bugfix suite (easy/medium/hard)
- [x] WS2 — offline solvability proof (fail buggy → pass reference fix, no vendor call)
- [x] WS3 — generic `run_task` + benchmark runner (solve rate by difficulty)
- [x] WS4 — live baseline (claude_code 0.667 @180s — real headroom)
- [x] WS5 — live skill A/B @240s (1.0/1.0 → hold)
- [x] WS6 — `acp eval benchmark-baseline` CLI + live scripts
- [x] WS7 — `benchmark` health section + `benchmark_baseline_present` production gate
- [x] WS8 — timeout-confound detector (0.667→1.0 gap = infra, not capability)
- [x] WS9 — underspecified multi-bug tier (two bugs, prompt names one)
- [x] WS10 — underspecified A/B → **PROMOTE** (0.444→1.0, p=0.0043, P=0.997)
- [x] WS11 — staged-canary deploy → `full_suite_discipline` deployed ACTIVE + persisted

## Live artifacts (secret-scanned, committed)

- [x] `reports/live/benchmark_baseline.json` (0.667; easy 1.0 / medium 0.5 / hard 0.5)
- [x] `reports/live/benchmark_skill_ab.json` (1.0/1.0, hold)
- [x] `reports/live/timeout_confound.json` (confounded=True)
- [x] `reports/live/underspecified_skill_ab.json` (lift 0.556, promote)
- [x] `reports/live/underspecified_promotion.json` (promoted + deployed)

## Operator commands

```bash
uv run acp eval benchmark-baseline --harness claude_code
uv run python evals/scripts/run_benchmark_baseline_live.py
uv run python evals/scripts/run_underspecified_skill_ab_live.py
uv run python evals/scripts/run_underspecified_promotion_live.py
```
