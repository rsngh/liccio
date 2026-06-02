# Alpha 8 report — learned governance from ACP's own exhaust

Alpha 7 made routing *policy-governed* (viability rules + an OPE promotion gate).
Alpha 8 makes that governance *learned and verifiable*: ACP now trains models on
its own run exhaust to predict viability, context strategy, evaluator trust, and
repair strategy — each behind a strict promotion contract — and every piece of
committed evidence is machine-checkable. See `ALPHA8_CHECKLIST.md` for the
workstream matrix and `GOALS.md` for the plan (Alpha 7 archived in `GOALS7.md`).

## The acceptance question

> Can ACP learn from its own exhaust to predict viability, context strategy,
> review need, evaluator trust, and repair strategy, while proving policy changes
> safely through OPE and live canaries?

## Headline results (committed artifacts)

- **Learned viability, safely gated** (`viability_learned_eval.json`): the learned
  assessor reaches 1.0 accuracy on the labeled set with **zero high-risk false
  negatives**, so it is `promotable` — but the `EnsembleViabilityAssessor` keeps
  it **advisory** (never overriding the rules' abstain / harness-required /
  human-review decisions) until that zero-FN bar is cleared. Safety is the gate,
  not accuracy alone.
- **Context strategy is learnable** (`context_strategy_learned_eval.json`): top-1
  strategy accuracy 1.0; the predictor recovers `test_focused` as best for bugfix.
- **Review burden drops without new risk** (`evaluator_trust_model.json`):
  risk-specific thresholds cut low-risk human-review burden by **33%** with **no**
  increase in false auto-approves.
- **Repair strategy classification** (`repair_classifier.json`): 0.95 accuracy
  over a 9-class failure taxonomy (logic_fix … not_automatable).
- **Canary rollback works** (`policy_canary_sim.json`): a reward-below-floor breach
  at the 50% stage triggers rollback; later stages are not executed.
- **Exploration is directed** (`exploration_plan.json`): under-sampled capability
  cells are flagged with concrete sample counts, a recommended exploring policy,
  and a cost estimate.
- **Every report is verifiable** (`artifact_manifest.json`, `acp reports
  validate`): 12/12 artifacts present, parse, and satisfy their schema; CI fails
  if a cited report goes missing or malformed.

## What's new since Alpha 7

- `observability/artifact_manifest.py` — schema registry + manifest + `acp reports
  manifest/validate`.
- `core/viability_learned.py` — Rule/Learned/Ensemble assessors + eval with the
  high-risk-FN promotion gate.
- `routing/context_strategy_learner.py` — learned strategy predictor + policy.
- `evaluation/evaluator_trust.py` — evaluator-correctness model + threshold policy.
- `evaluation/repair_classifier.py` — repair-strategy taxonomy + classifier.
- `training/dataset_factory.py` — completed `viability` / `context_strategy` /
  `trace_summary` / `verification_plan` builders.
- `training/model_governance.py` — `ModelPromotionGate` + `MemorizationAudit`.
- `routing/canary.py` + `routing/exploration.py` — canary executor + coverage-gap
  analyzer.

## Honest limitations

- The learned models are trained/evaluated on synthetic or small distilled sets so
  the artifacts are deterministic and auditable; real promotion needs the
  capability-matrix population campaign (more logged traffic).
- Local LoRA fine-tuning remains a gated smoke path (no GPU here): the pipeline
  builds + audits data and *gates* promotion, but does not train in CI.
- The ensemble viability assessor stays advisory by design until live high-risk
  outcomes confirm zero false negatives — the safe default.
- Several Alpha-8 plan workstreams (Docker live security gate, storage/scale
  benchmark, prompt-injection benchmark, repo memory boundary, full review-studio
  product API) are scoped but deferred; the learned-governance core is complete.
