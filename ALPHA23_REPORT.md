# Alpha 23 — Graded Live Benchmark & Honest Skill-Lift Measurement

**Mission:** Alpha 22 surfaced a gap — every live skill canary held at lift 0.0 because the
single divide fixture was at *ceiling* for a strong vendor harness, so no skill could ever
earn a promotion on live evidence. Alpha 23 replaces it with a **difficulty-stratified
benchmark**, measures harness capability and skill lift **honestly**, and lets the
governance loop promote a skill *only if* a tier with real headroom shows measured lift —
and hold (truthfully) otherwise.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1/2 | Graded suite | `benchmark_suite.py` — 6 tasks (easy `divide`/`factorial`, medium `slugify`/`chunk`, hard `roman`/`merge_intervals`); every task proven offline to fail buggy + pass its reference fix (no vendor call). |
| 3 | Benchmark runner | `VendorNativeHarness.run_task` (generic) + `benchmark_runner.run_benchmark` — solve rate overall + per difficulty via the hygiene layer (conclusive only; timeouts excluded). |
| 4 | Live baseline | claude_code over the suite @180s: **overall 0.667** (easy 1.0 / medium 0.5 / hard 0.5) — real headroom, not at ceiling. |
| 5 | Live skill A/B | verify-and-edge-cases skill @240s: baseline 1.0 vs skill 1.0 → **lift 0.0, hold**. |
| 6 | CLI + scripts | `acp eval benchmark-baseline`; live baseline + A/B scripts. |
| 7 | Health + gate | `benchmark` health section + `benchmark_baseline_present` production gate (real graded baseline required; skill-lift reported, not gated). |
| 8 | Timeout-confound detector | `infra_confound.detect_timeout_confound` — the WS4 0.667→1.0 gap **closes** when the budget is relaxed 180→240s ⇒ **infra-confounded**, not capability. |
| 9 | Underspecified tier | `UNDERSPECIFIED_TASKS` (stats/textutil/bank) — two bugs per module, prompt names only one; a real, non-timeout gap that isolates skill discipline. |
| 10 | Underspecified A/B | live full-suite-discipline skill vs baseline: **baseline 0.444 → skill 1.0, lift 0.556, p=0.0043, P(better)=0.997 → PROMOTE**. |
| 11 | Loop closed | drove that promote through the staged canary (5/25/50/100%): all stages advanced → `full_suite_discipline` **deployed ACTIVE**, `SkillCanaryRun` persisted. First skill promoted on live evidence. |

## The central result — honest measurement promotes *and* holds

Strong vendor harnesses sit at or near **ceiling** on direct bugfix tasks at a fair time
budget, so a verify skill shows **no** lift there (WS5: hold). Apparent capability gaps under
tight timeouts are **infra artifacts** (the hard `roman` task ran 158s under a 180s cap),
which the new timeout-confound detector flags automatically (WS8). But when the gap is
**real and not timeout-confounded** — an underspecified prompt that names one bug while a
second genuinely fails — the full-suite-discipline skill produces a large, significant lift
(WS10: 0.444→1.0) and the governance loop **promotes and deploys** it end-to-end (WS11).

This is the world-defining property: the platform **fabricates nothing**. It holds when a
skill adds no measured value, refuses gaps that are really infra, and promotes — through a
guardrail-checked staged canary, with a persisted audit trail — exactly when the lift is
real. Alpha 22 proved it *holds*; Alpha 23 proves it also *promotes*, for the right reason.

## Gate

```
uv run pytest -q --timeout=300         # full suite
uv run ruff check . && uv run mypy src # clean
uv run alembic upgrade head            # OK
uv run acp reports validate            # artifacts valid (incl. benchmark_* + timeout_confound)
uv run acp eval benchmark-baseline --harness claude_code
```

## Fail-closed posture

Production health now also requires a real difficulty-stratified benchmark baseline on disk
(`benchmark_baseline_present`). Whether a skill helps is **reported**, never **gated** — a
no-lift result is honest, not a failure.
