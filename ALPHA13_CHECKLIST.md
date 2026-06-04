# Alpha 13 / Round 13 — Measurement-Trustworthy Preproduction Router Checklist

Status: COMPLETE. Gate green (829 passed, 5 skipped, ruff+mypy clean across 223 src,
alembic OK, 42 artifacts valid). See `ALPHA13_REPORT.md`.

## Workstreams

- [x] WS1 — release synchronization (CURRENT_STATUS + pytest report)
- [x] WS2 — AttemptOutcome as the mandatory learning gate (`evaluation/learning_gate.py`)
- [x] WS3 — measurement-quality scoring (`MeasurementQualityScore` 8 dims + policy)
- [x] WS4 — capability matrix v3 (provider_failure_rate, cost_per_attempt, measurement_quality_mean)
- [x] WS5 — cost-aware OPE v3 (cost/latency/quality on samples + 5 objective profiles)
- [x] WS8 — HAR/HFR/PWL + measurement quality in the health snapshot
- [x] WS9 — policy dossier v3 (measurement-quality section on the live endpoint)
- [x] WS10 — production health gate `measurement_quality_trusted`
- [x] WS11 — measurement mutation suite v2
- [x] WS12 — live cell ingestion (bakeoff -> DB via `ingest_attempt_outcomes`)
- [x] WS13 — live corpus expansion (refactor + ci_fix; 6 task types)
- [x] WS17 — relative trajectory judge -> preference learning
- [x] WS6/WS7/WS18 — provider policy, availability/activation, harness-evolution PR pipeline (prior rounds)

## Committed live artifacts (secret-scanned)

- [x] `evals/reports/measurement_quality.json` — overall 1.0, trusted=true
- [x] `evals/reports/measurement_hygiene.json` — conclusive, not contaminated
- [x] `evals/reports/harness_availability_audit.json` — both harnesses, not degraded
- [x] `evals/reports/tool_activation_metrics.json` — activated, 0 failures

## Gate

```bash
uv run pytest -q --timeout=300         # 829 passed, 5 skipped
uv run ruff check . && uv run mypy src # clean (223 src)
uv run alembic upgrade head            # OK
uv run acp reports validate            # 42 artifacts valid
```
