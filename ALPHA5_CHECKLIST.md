# Alpha 5 — production-grade empirical routing lab: PR / merge checklist

Alpha 5 turns ACP from a "two-harness alpha" into a repeatable **empirical
routing lab**: compare multiple real harnesses across a no-patch dataset, learn
from traces *and* delayed outcomes, calibrate every evaluator, and enforce hard
budget + sandbox limits.

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| 1 | `docs/status_schema.md` (7-category status vocabulary) + `test_docs_consistency.py` (status-schema, pass-count-matches-reports, no stale claims). |
| 2 | Live artifact discipline: `observability/live_report.py` redaction + committed **redacted OpenAI-vs-Claude bakeoff** showing both solved the same no-patch task (tool calls / changed files / tokens / cost / latency / verification). |
| 5 | `evals/datasets/no_patch_tasks.yaml` across all six task types + 5 fixture-repo generators; no task carries `metadata.files`/`patch` (enforced). |
| 6 | Dataset-driven **bakeoff engine v2** (`bakeoff_v2.py`) with repetitions + per-task/per-adapter/per-run metrics + aggregates by adapter/task_type/risk; CLI `acp eval multi-harness-bakeoff`. |
| 7 | **Router learning from traces**: `trace_features.py` (per adapter×task_type history) + `PolicyObservation` provenance/trace-features; CLI `acp policy replay-eval`. Replaying changes the preferred harness per task class. |
| 8 | **Delayed outcome simulator** (`postmerge_sim.py`): synthetic merged/reverted/incident/reopened/latency-regression outcomes downgrade a day-0 favourite; CLI `acp eval simulate-postmerge`. |
| 9 | **Calibration v2** (`calibration_v2.py`): per-evaluator accuracy/precision/recall/Brier/ECE/correlation + recommended human-review threshold + false-auto-approve risk. |
| 10 | **Sandbox red-team lab** (`sandbox_redteam.py`): safe local probes verify containment; destructive attacks listed as not-enforceable locally → local marked unsafe for true harnesses; Docker enforces. |
| 11 | Service markers (`live_pgvector`/`live_qdrant`/`live_otlp`) + no-silent-fallback (`PgVectorStore(require_real=True)` raises instead of degrading to memory). |
| 12 | **Budget ledger + hard-stops** (`core/budget.py`): harness loop stops on cost/wall/steps/tool_calls with a structured `budget_exceeded:<resource>` error and a bounded trace; violations audited. |
| 15 | This checklist + `ALPHA5_REPORT.md` + `make alpha5-artifacts`. |

## Required artifacts (committed under `evals/reports/` + `reports/`)

- [x] `reports/pytest.txt`, `reports/coverage.txt`
- [x] `evals/reports/multi_harness_v2.json`
- [x] `evals/reports/router_replay.json`
- [x] `evals/reports/calibration_v2.json`
- [x] `evals/reports/sandbox_redteam.json`
- [x] `evals/reports/postmerge_sim.json`
- [x] `reports/live/live_openai_claude_bakeoff.json` (redacted, real run)
- [x] `evals/reports/docker_security.json` (explicit skip when Docker absent)

## Gate

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha4-artifacts
make alpha5-artifacts
```

Optional live gates: `make live-openai` · `make live-second-harness` ·
`make live-docker` · `make live-qdrant` · `make live-pgvector`.

## A reviewer can now answer

- **Which harness is best for each task type?** → `multi_harness_v2.json` (by_task_type).
- **Why did the router choose it?** → `router_replay.json` (preference changes) + trace features.
- **What did it cost?** → per-cell cost/tokens/latency + the redacted live bakeoff.
- **How was it verified?** → verification_pass + evidence in the run graph.
- **Did the evaluator agree with humans?** → `calibration_v2.json` (per-evaluator).
- **Did delayed outcomes change the ranking?** → `postmerge_sim.json` (downgrade).
- **Is local execution safe for true harnesses?** → `sandbox_redteam.json` (no — use Docker).
