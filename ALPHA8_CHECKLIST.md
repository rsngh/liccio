# Alpha 8 — learned governance + training platform: PR / merge checklist

Alpha 8 moves ACP from a *policy-governed* lab to a *data-driven, learned*
platform: it learns viability, context strategy, evaluator trust, and repair
strategy from its own exhaust, gates every learned model behind a promotion
contract, and makes all evidence machine-verifiable. Status vocabulary:
`docs/status_schema.md`.

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| 1 | **Artifact truth infra** (`observability/artifact_manifest.py`): `ReportSchemaRegistry` + `validate_artifact` + `build_manifest` (path/hash/size/generated_at/summary). CLI `acp reports manifest` / `acp reports validate` (CI-failing). |
| 2 | **Learned viability** (`core/viability_learned.py`): Rule/Learned/**Ensemble** assessors; ensemble is advisory until **zero high-risk false negatives** on holdout; eval report (accuracy/precision/recall/Brier/ECE/abstention/human-review-recall/high-risk-FN). |
| 3 | **Context-strategy learner** (`routing/context_strategy_learner.py`): reward predictor + policy + top-1 eval. |
| 4 | **Evaluator trust model** (`evaluation/evaluator_trust.py`): predicts P(evaluator correct) + risk-specific human-review thresholds. |
| 5 | **Repair-strategy classifier** (`evaluation/repair_classifier.py`): 9-class taxonomy from task + trace + failure output. |
| 6 | **Dataset factory completion**: real builders for `viability` / `context_strategy` / `trace_summary` / `verification_plan`. |
| 8 | **Fine-tuning governance** (`training/model_governance.py`): `ModelPromotionGate` (beats rules + prompt baselines, temporal + repo holdout, leakage + memorization audits, no high-risk degradation, cost/latency caps, rollback plan) + `MemorizationAudit`. |
| 10 | **Policy canary simulator** (`routing/canary.py`): staged rollout with guardrail-driven rollback. |
| 12 | **Exploration designer** (`routing/exploration.py`): `CoverageGapAnalyzer` → which cells need how many more samples, which policy, cost, risk. |
| 7 | **Local training path** (gated): `training/{local_lora,local_eval,model_registry,model_card}.py` — skips cleanly without torch/peft; eval feeds the model-promotion gate. CLI `acp train local-lora`. |
| 9 | **Vendor harness hardening**: parametrized offline contract test (codex_cli + claude_agent_sdk) + key/binary-gated live codex smoke (skipped by default). |
| 11 | **Real-log OPE expansion**: +exploration-preserving variant; per-policy overlap-aware trust gate (greedy no longer trusted at zero overlap) + exploration recommendation. |
| 13 | **Capability-matrix population campaign**: 270 sufficient cells; gaps explained. CLI `acp eval capability-campaign`. |
| 14 | **Docker live security gate**: `run_docker_security_live` + `DockerSecurityGate.production_allowed` (refuses real-harness prod without a passing report). CLI `acp eval docker-security-live`. |
| 15 | **Review-studio product API** (FastAPI): `/reviews/queue|bundle|label|make-eval-case|make-training-example|calibrate`. |
| 16 | **Observability export**: `export_traces` (jsonl/otlp), `export_eval` (json/parquet-gated), honest exporter health. CLI `acp train observability-health`. |
| 17 | **Storage/scale benchmark**: per-N latencies + sub-quadratic verdict. CLI `acp eval scale-benchmark`. |
| 18 | **Security/prompt-injection benchmark**: 8 attacks all escalated/flagged, zero secret leak. CLI `acp eval security-benchmark`. |
| 19 | **Repo memory boundary**: private repos excluded from the global pool; deterministic holdout; memorization canary. |
| Capstone A | **Closed-loop self-improvement** (`learning/self_improvement.py`): learn viability + context-strategy from exhaust, evaluate, gate promotion (advisory unless zero high-risk FN). CLI `acp train self-improve`. |
| Capstone B | **Explainable Decision Card** (`core/decision_card.py`): per-task viability + capability-matrix recommendation (no low-sample overclaim) + verification + rationale. CLI `acp viability decision-card`. |
| 20 | This checklist + `ALPHA8_REPORT.md` + `make alpha8-artifacts` (16 artifacts, `acp reports validate`) + docs-consistency extension. |

## Required artifacts (committed)

- `evals/reports/artifact_manifest.json` — manifest over all reports (12/12 valid).
- `evals/reports/viability_learned_eval.json` — learned viability eval (acc 1.0, high-risk FN 0.0, promotable).
- `evals/reports/context_strategy_learned_eval.json` — top-1 strategy accuracy (1.0; best bugfix = test_focused).
- `evals/reports/evaluator_trust_model.json` — −33% low-risk review burden, no extra false auto-approves.
- `evals/reports/repair_classifier.json` — 0.95 rule accuracy across 9 classes.
- `evals/reports/policy_canary_sim.json` — guardrail breach → rollback at the 50% stage.
- `evals/reports/exploration_plan.json` — under-sampled cells flagged with sample counts.

## Gate

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha7-artifacts
make alpha8-artifacts
make reports-validate
```

## Reviewer questions answered

- Can ACP learn viability from exhaust without unsafe optimism? → `viability_learned_eval.json` (zero high-risk false negatives gate; ensemble stays advisory otherwise).
- Which context strategy per task type? → `context_strategy_learned_eval.json`.
- Can review burden drop safely? → `evaluator_trust_model.json`.
- Is a fine-tuned model safe to promote? → `ModelPromotionGate` (WS8) + `MemorizationAudit`.
- Is every cited report real and consistent? → `acp reports validate` / `artifact_manifest.json`.
