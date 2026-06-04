# Alpha 13 / Round 13 — Measurement-Trustworthy Preproduction Router

**Mission:** turn ACP from a measurement-aware alpha lab into a **measurement-trustworthy
preproduction router** — one that runs live harnesses, classifies measurement failures
correctly, enforces provider/sandbox budgets, persists clean evidence, updates routing
**only** from trustworthy outcomes, and explains every production routing decision.

This round hardens the Round 12 measurement-trust layer into a *mandatory learning gate*
and adds a measurement-quality trust score that the production health gate enforces.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1 | Release sync | CURRENT_STATUS + reports/pytest.txt to Round 12 truth; docs-consistency green. |
| 2 | Learning gate | `AttemptOutcomeRecord` eligibility fields (conclusive, contaminated, infra/provider_failure_kind, *_valid, include_in_quality/reliability_denominator) + `evaluation/learning_gate.py` — the single chokepoint so only conclusive attempts update solve-rate. |
| 3 | Measurement-quality scoring | `MeasurementQualityScore` (8 dims) + `MeasurementQualityPolicy` + `measurement_quality_report`. |
| 4 | Capability matrix v3 | `conclusive_failure_rate`, `provider_failure_rate`, `cost_per_attempt`, `measurement_quality_mean`; recommendations stable under injected infra noise. |
| 5 | Cost-aware OPE v3 | `OPESample` carries cost/latency/measurement_quality; 5 objective profiles (`quality_max`, `cost_saver`, `balanced`, `risk_min`, `measurement_trust_max`). |
| 8 | HAR/HFR/PWL in health | Health `measurement` section surfaces per-adapter harness-benefit + measurement-quality overall. |
| 9 | Policy dossier v3 | Live `policy_dossier(run_id)` attaches the measurement-quality section ("why trust this evidence"). |
| 10 | Production health gate | `measurement_quality_trusted` gate (reads `measurement_quality.json`). |
| 11 | Mutation suite v2 | Every mutation is caught by the measurement-QUALITY layer + provider-policy contract. |
| 12 | Live cell ingestion | Bakeoff `ACP_BAKEOFF_PERSIST` ingests classified `AttemptOutcome` rows into a DB; `hygiene_from_store` reads them back. |
| 13 | Live corpus expansion | Added `refactor` + `ci_fix` live tasks (behavior-preserving refactor, red-CI off-by-one). |

(WS6 provider-policy enforcement and WS7 harness availability/activation were delivered in
Round 12 and extended here.)

## Live validation (real OpenAI + Anthropic harnesses)

A live bakeoff (`ACP_BAKEOFF_PERSIST=1`) produced, secret-scanned and committed:

- `measurement_quality.json` — all 8 trust dimensions 1.0, overall 1.0, **trusted=true**.
- `measurement_hygiene.json` — 36/36 conclusive, solve_rate 0.972, contaminated=false.
- 36 `AttemptOutcome` rows persisted to a DB and read back (`hygiene_from_store`: n=36).
- Production health gate `measurement_quality_trusted=true` on the real artifact.

## Gate

```
uv run pytest -q --timeout=300   # 826 passed (+ a Docker concurrency flake that passes in isolation)
uv run ruff check .              # clean
uv run mypy src                  # clean, 223 source files
uv run alembic upgrade head      # OK (fresh DB)
uv run acp reports validate      # all 42 artifacts valid
```

## Honest status / remaining

Delivered: WS1–5, 8–13. Remaining (larger / environment-gated): WS14 (Docker live-security
gate), WS15 (vendor harness live campaign), WS16 (fully *learned* topology actions — the
safety gate shipped in Round 12), WS17 (relative trajectory judge integration — module
exists), WS18 (harness-evolution PR pipeline — governance scaffold exists), WS19 (local LoRA
pilot). These are honestly labeled, not claimed.
