# Alpha 7 — policy-governed routing + training pipeline: PR / merge checklist

Alpha 7 turns the self-improving lab (Alpha 6) into a **policy-governed platform**
with explicit viability classification, an OPE promotion gate, and a training-data
/ fine-tuning pipeline distilled from ACP run exhaust. Status vocabulary:
`docs/status_schema.md`.

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| 1 | **ViabilityAssessment** primitive: `schemas/viability.py` + deterministic `core/viability.py` (cheap-vs-harness, abstain on unverifiable/ambiguous tasks), produced at the classify node, persisted (`viability_assessments` table, migration `f7a2c9d1e004`), surfaced in `full_run_graph`, and consumed by routing to narrow the context-strategy space. |
| 2 | **CapabilityMatrix** (`routing/capability_matrix.py`): empirical metrics per `(task_type × risk × repo_type × agent_class × context_strategy × verification_policy)` from bakeoff reports + post-merge folding, with low-sample flagging (no overclaim). CLI `acp viability matrix`. |
| 3/4/18 | **Training-data factory** (`training/`): `TrainingExample`/`DatasetVersion` schemas, `DatasetFactory` (temporal+repo split, dedup, redaction, leakage audit), OpenAI/HF JSONL exporters, candidate report, gated LoRA smoke. CLI `acp dataset build`, `acp train candidate-report`. |
| 5 | **OPE promotion gate** (`routing/promotion.py`): statistical-trust (ESS / overlap / max-weight / DR-CI-beats-baseline / SNIPS-agrees) + operational-safety (cost cap / human-review-not-worse / high-risk-not-degraded / calibration) conditions → promote/block + staged canary plan. CLI `acp policy promotion-check`. |
| 6 | **Real-log OPE report**: `AppService.real_log_ope_report` compares random/greedy/supervised on the real persisted log and refuses to rank when overlap/ESS too poor. CLI `acp policy real-log-ope`. |
| 7 | **Context-strategy DOWNSTREAM benchmark** (`evaluation/context_downstream_benchmark.py`): scores strategies by actual task success/reward, not just retrieval recall. CLI `acp eval context-downstream-benchmark`. |
| 8 | **Vendor harness hardening**: `codex_cli` is a real (mediated, budget/timeout-bounded) vendor loop; `claude_agent_sdk` capability-gated. |
| 9 | **Human-review studio**: secret-free bundle, `make_eval_case`, and `make_training_example` (label → redacted `human_review` TrainingExample). CLI `acp reviews bundle / make-eval-case / make-training-example`. |
| 19 | This checklist + `ALPHA7_REPORT.md` + `make alpha7-artifacts` + docs-consistency extension. |

## Required artifacts (committed)

- `evals/reports/real_log_ope.json` — multi-policy OPE + promotion gate (greedy blocked for overlap; exploration-smoothed supervised promoted).
- `evals/reports/viability_matrix.json` — capability matrix + a sample viability assessment.
- `evals/reports/training_candidate_report.json` — fine-tuning candidate report.
- `evals/reports/vendor_harness_smoke.json` — vendor adapter capability + availability.
- `evals/reports/context_downstream_benchmark.json` — downstream strategy benchmark.
- `reports/live/alpha7_openai_experiment.json` — redacted live decision slice (viability → real OpenAI solve → distilled training example).

## Gate

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha6-artifacts
make alpha7-artifacts
```

## Reviewer questions answered

- Should we deploy this policy? → `real_log_ope.json` promotion gate (block/promote + reasons + canary plan).
- What can ACP attempt, and when should it abstain or require a human? → `ViabilityAssessment` in every run graph.
- Which `(agent, context_strategy)` is best per task type/repo, with enough samples to trust? → `viability_matrix.json` (low-sample cells flagged).
- Is there enough clean exhaust to fine-tune a local model? → `training_candidate_report.json`.
