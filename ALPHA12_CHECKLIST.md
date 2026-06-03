# Alpha 12 — harness quality + workflow-shape learning: checklist

Alpha 12 adds the genuinely-new Alpha 11/12 workstreams on top of the Alpha-11
production-readiness base: harness quality metrics, a governed harness-evolution
pipeline, workflow-shape (topology) action learning, and a relative trajectory
judge. (The other Alpha 11/12 plan items — dossier, Pareto config, Docker/vendor
live, preference governance, drift persistence, exploration executor, scheduler,
data-governance red-team, mixed corpus, health modes, operator API, policy pack,
release bundle — landed in Round 11; LoRA remains GPU-gated.)

## Workstreams delivered (the new core)

| WS | Delivered |
| --- | --- |
| 6 | **Harness activation/adherence metrics** (`evaluation/harness_metrics.py`, `schemas/harness_metrics.py`): HAR (activation rate), HFR (following rate), PWL (pass-when-loaded), phase adherence, decay; by model/harness/task_type. CLI `acp eval harness-metrics`. |
| 7 | **Harness evolution pipeline** (`training/harness_evolution.py`): proposal → scan (redact + security) → eval (regression + negative-transfer) → review → canary → rollback. No promotion without eval + audit + rollback. |
| 8 | **Topology action learning** (`schemas/routing.py` `TOPOLOGY_ACTIONS` + `RoutingAction.topology`, `routing/actions.py`): the router can learn workflow shape (skip planner/reviewer, light/strict verifier, branch_parallel, terminate, abstain) — backward-compatible arm keys, OPE-learnable. |
| 9 | **Relative trajectory judge** (`evaluation/trajectory_judge.py`): compares two trajectories on 8 axes (goal/test/minimality/security/activation/adherence/recovery/cost) + cross-judge audit + reward sensitivity; feeds preference learning. CLI `acp eval trajectory-judge`. |

## Live evidence (real keys)

- `reports/live/alpha12_harness_metrics.json` — REAL openai+claude harness traces on
  2 no-patch tasks: **HAR=1.0, HFR=1.0, PWL=1.0** (both activated the tool loop,
  followed read→write→run, and solved). Redacted, no secret leak.

## Required artifacts (manifest-validated, 38/38)

- `evals/reports/harness_metrics.json`, `evals/reports/trajectory_judge.json`,
  `reports/live/alpha12_harness_metrics.json`.

## Gate

```bash
uv run pytest -q --timeout=300 && uv run ruff check . && uv run mypy src
uv run alembic upgrade head && acp reports validate
```
