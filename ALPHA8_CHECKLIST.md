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
| 20 | This checklist + `ALPHA8_REPORT.md` + `make alpha8-artifacts` + docs-consistency extension. |

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
