## Executive assessment

The branch is now in a materially different category than the early agent-control-plane prototype. Based on the current `feat/agent-control-plane` files and your Alpha 7 sprint note, this is best described as:

> **Alpha 7: a policy-governed, self-improving routing lab with explicit viability assessment and a training-data pipeline from agent exhaust.**

The implementation now covers most of the original plan’s control-plane thesis: task viability, agent/context routing, evals, verification, human review, OPE-based policy gating, provenance, training-data extraction, multi-harness traces, and live no-patch harness evidence. The branch reports **498 passing tests, 7 skipped, ruff/mypy clean, and Alembic upgrade OK**. 

The biggest shift in Alpha 7 is that the project no longer merely routes and measures. It now asks: **should we even attempt this task, and is the routing policy safe enough to promote?** That is exactly the right direction.

I would still call this an **alpha lab**, not production. The remaining gaps are no longer “basic architecture missing”; they are higher-order: real-world logged data volume, live Docker/security validation, vendor harness maturity, policy trust under poor overlap, learned viability models, broader no-patch task corpora, and end-to-end fine-tuning/evaluator-training loops.

One housekeeping note: your latest message says `feat/acp-round6` still had a finalize/coverage refresh pending, but the current `feat/agent-control-plane` files I inspected already show Alpha 7 with 498 tests and coverage linked from `CURRENT_STATUS.md`.  If there is another local finalize commit not yet pushed, I would still wait and fast-forward once, but the remote branch I inspected is coherent enough for review.

---

# What has been implemented

## 1. Alpha 7 status and test gate

`CURRENT_STATUS.md` now states Alpha 7 status and reports:

```text
498 passing
7 skipped
ruff clean
mypy clean
Alembic upgrade head included in the gate
```



The committed `reports/pytest.txt` confirms:

```text
498 passed, 7 skipped, 1 warning in 1173.50s
ruff clean
mypy clean
156 src files
alembic upgrade head: OK
```



Coverage is still shown as Alpha 6’s report at 87%, so if Alpha 7 coverage has not been refreshed, that should be finalized before PR review. 

## 2. Viability assessment is now first-class

This directly answers the previous conceptual question: “Can the system classify which requests are viable for which model/context/verification route?”

Yes, now there is a concrete `ViabilityAssessment` schema. Its docstring says the control plane decides whether and with what resource class a task is viable to automate before routing, and that the result narrows viable agent classes/context strategies, marks cheap-model vs true-harness requirements, human review, and abstention reasons. 

The schema includes:

```text
task_type
risk_level
ambiguity_score
testability_score
available_evidence
viable_agent_classes
viable_context_strategies
required_verification
capability_requirements
model_strength
cheap_model_viable
true_harness_required
human_review_required
parallelism_recommended
abstain
abstention_reasons
confidence
supporting_features
```



This is a major architectural step. Earlier, viability was an emergent property of routing/eval results. Now it is an explicit, persisted decision artifact.

## 3. Viability is integrated into Alpha 7 workflow claims

`ALPHA7_CHECKLIST.md` says `ViabilityAssessment` is produced at the classify node, persisted in a `viability_assessments` table, surfaced in the full run graph, and consumed by routing to narrow context-strategy space. 

`ALPHA7_REPORT.md` says docs/low-risk work maps to cheap simple-model viability, security/high-risk maps to true harness + strict verification + human review, and no spec/no tests maps to abstention/spec inference. 

This is exactly the kind of request→capability classification the original plan needed.

## 4. Capability matrix exists

The capability matrix aggregates empirical evidence per routing cell:

```text
task_type × risk_level × repo_type × agent_class × context_strategy × verification_policy
```

and stores metrics like success rate, cost, latency, human-review rate, post-merge failure rate, OPE reward, calibration confidence, sample size, and last updated. 

It explicitly refuses to overclaim: cells below the minimum sample size are flagged as `low_sample` and `best_for` refuses to recommend them. 

That is an excellent product primitive. It turns “which agent/context should handle this?” into a queryable evidence table.

## 5. OPE promotion gate is implemented

`routing/promotion.py` turns offline policy evaluation into a promotion/block decision. The module explicitly says high point estimates are not enough: a policy must pass statistical trust and operational safety checks. 

The gate checks:

```text
effective sample size
propensity overlap
max importance weight
DR CI lower bound vs baseline
SNIPS agreement
cost cap
human-review rate cap
high-risk not degraded
calibration confidence
```

 

This is one of the most important pieces in the whole branch. It prevents the router from deploying a “better” policy based on misleading offline estimates.

## 6. Real-log OPE and promotion logic are now part of the story

`ALPHA7_REPORT.md` says the committed real-log OPE report blocks the deterministic greedy policy for poor overlap while promoting an exploration-smoothed supervised policy. The reported result is exactly the behavior you want: a policy with a slightly lower point estimate but better overlap/trust gets promoted over an overconfident low-overlap greedy policy. 

This is a meaningful maturity jump from “we can calculate OPE” to “we can make deployment decisions from OPE.”

Caveat: I was able to verify the checklist references the committed artifacts, but the connector could not fetch some `evals/reports/*.json` artifact paths directly. Before merge, add or run an artifact-path test ensuring every checklist artifact exists at the exact referenced path. The checklist names `real_log_ope.json`, `viability_matrix.json`, `training_candidate_report.json`, `vendor_harness_smoke.json`, `context_downstream_benchmark.json`, and `alpha7_openai_experiment.json`. 

## 7. Training-data factory exists

The training module is now real enough to review. Its package docstring says it turns persisted ACP run exhaust—traces, evaluations, weak/human labels, routing decisions, rewards—into versioned, redacted, leakage-audited training datasets, JSONL exporters, and a fine-tuning candidate report. 

`dataset_factory.py` is a substantial implementation. It consumes persisted entities, supports deterministic temporal and repo splits, deduplication, redaction, generated-file filtering, and leakage audit. 

It supports dataset kinds:

```text
viability
routing
context_strategy
human_review
evaluator
repair
trace_summary
verification_plan
```



Important caveat: several distillers are still stubbed. The code returns empty lists for `viability`, `context_strategy`, `trace_summary`, and `verification_plan`, with comments saying those require additional linkage/signals. 

So: the training factory architecture is implemented, but only some dataset kinds are mature.

## 8. Live OpenAI decision slice exists

The committed Alpha 7 live artifact shows a real OpenAI harness run with viability, harness solve, verification, and distilled repair training example:

```text
task_type: bugfix
true_harness_required: false
viable_context_strategies: bug_reproduction, test_focused, hybrid_keyword_embedding
adapter: openai_harness
solved: true
verified_raises_on_zero: true
tool_calls: 1
changed_files: calculator.py
estimated_cost_usd: 0.000385
distilled_training_example: repair
```



This is an excellent “thin vertical slice” artifact: viability → harness action → verification → training example.

## 9. Context-strategy benchmark has moved beyond recall

Alpha 6 already added recall/MRR/token/latency benchmarking. Alpha 7 adds a downstream context benchmark. The checklist says `context_downstream_benchmark.py` scores context strategies by actual task success/reward, not just retrieval recall. 

That is important because retrieval metrics alone can be misleading. The right product metric is downstream task outcome per token/cost.

## 10. Vendor harness category is advancing

Alpha 7 claims `codex_cli` is now a real mediated, budget/timeout-bounded vendor loop, while `claude_agent_sdk` remains capability-gated. 

The report is honest that `codex_cli` is real “in shape” but not yet proven against a full production Codex session, and that `claude_agent_sdk` remains scaffolding. 

This is the right distinction.

## 11. Review studio is no longer just labeling

Alpha 7 says the review studio can produce a secret-free bundle, make eval cases, and make training examples from human labels. 

That is a critical feedback-loop feature: human review should not just approve/reject; it should create reusable training/eval data.

## 12. The sprint builds on the prior Alpha 4/5 foundations

The prior sprint reports show the project already shipped two ACP-native true harnesses, normalized traces, a multi-harness bakeoff, and router learning from bakeoffs in Alpha 4, then no-patch datasets, trace-feature routing, delayed outcomes, calibration, sandbox red-team, budget ledger, and live OpenAI-vs-Claude evidence in Alpha 5.  

Alpha 7 is a coherent continuation: it adds policy governance and training-data extraction on top of that empirical routing lab.

---

# What has not been implemented or remains weak

## 1. The viability assessor is still deterministic, not learned

This is explicitly listed as an honest limitation: the viability assessor is deterministic rules, and a learned classifier is a natural next target for the new viability dataset kind. 

That is fine for Alpha 7, but it should not be mistaken for a trained viability model.

## 2. Several training dataset kinds are still stubs

The training factory supports the right dataset-kind names, but the source shows some builders return empty lists:

```text
viability
context_strategy
trace_summary
verification_plan
```



This means the fine-tuning pipeline is structurally present, but not yet full-spectrum. The most important next dataset kind is **viability**, followed by **context_strategy** and **evaluator**.

## 3. Fine-tuning itself is only a gated smoke path

`ALPHA7_REPORT.md` says LoRA fine-tuning is a gated smoke path, there is no GPU in the environment, and CI does not actually train. The pipeline produces and audits data and recommends when to train. 

That is reasonable, but it means the branch has a **training-data factory**, not yet a working local model-improvement loop.

## 4. Vendor harnesses are not yet production-proven

`codex_cli` is described as a real mediated loop in shape, but not yet proven against a full production Codex session; `claude_agent_sdk` remains capability-gated scaffolding. 

This is now probably the biggest product-readiness gap.

## 5. Docker remains skipped in the committed test run

The test report says Docker workspace tests are skipped, along with live pgvector and live codex CLI. 

That is acceptable for normal local CI, but not acceptable as the final safety proof for running untrusted real agents.

## 6. Some referenced artifacts should be path-verified

The checklist requires several artifacts under `evals/reports/`.  I could inspect the live Alpha 7 OpenAI artifact directly, but could not fetch some of the `evals/reports/*.json` paths through the connector. This may be a connector/path issue, but CI should enforce artifact existence and schema validation regardless.

## 7. Real-world data volume is still likely too small

The current OPE and promotion-gate results are important, but they appear based on controlled/synthetic logs. Alpha 7 is honest that the OPE headline uses a synthetic separable log and that real-log OPE will report untrustworthy until there is enough exploratory traffic. 

That is the right caution. The next step is to generate much more real logged traffic with deliberate exploration.

## 8. Human-review training loop needs scale and UI/productization

The review studio can produce eval/training examples, but the bigger product feature is a review queue that developers actually use. The backend needs volume, ergonomics, and calibration outcomes.

## 9. Capability matrix needs real sample sizes

The matrix is conservative, which is good. But its value depends on non-low-sample cells. Right now, given the project’s stage, many cells will likely be low-sample. The next push should fill those cells with repeated no-patch bakeoffs and live/semi-live experiments.

---

# Constructive feedback

## 1. Move from “Alpha lab” to “policy-governed experiment platform”

The project should now be described as:

> **A policy-governed experimentation platform for routing software-engineering tasks across agent harnesses, context strategies, and verification policies.**

Do not call it production. Do call it a **policy-governed routing lab**.

## 2. Make artifact-path validation a hard CI gate

The checklist now references many artifacts. Add a test that reads every `ALPHA*_CHECKLIST.md`, extracts paths, and verifies:

```text
file exists
JSON validates if .json
schema validates if known report type
headline numbers match markdown claims
```

This would catch missing or stale artifacts.

## 3. Treat OPE promotion as a guardrail, not a proof

The promotion gate is exactly right, but now make it harder to satisfy:

```text
require temporal holdout
require high-risk slice non-degradation
require cost cap
require human-review cap
require calibration floor
require no zero-overlap task classes
require delayed-outcome replay
```

The current gate has hooks for many of these; the next step is to require them in realistic policy promotion.

## 4. Learn the viability assessor next

This is the most natural next ML move.

The deterministic viability rules should create labels. Then train and evaluate:

```text
rules-only baseline
supervised lightweight classifier
LLM judge/classifier
fine-tuned local small model
ensemble
```

The target is not “replace rules.” The target is:

```text
identify ambiguous cases
estimate confidence
spot out-of-distribution tasks
recommend abstention
route to spec-generation first
```

## 5. Make the training factory produce non-empty datasets for all promised kinds

Prioritize:

```text
viability
context_strategy
evaluator
trace_summary
verification_plan
```

Right now, the interface is ahead of the implementation for some of these kinds. Close that gap.

## 6. Expand no-patch task data aggressively

The control plane’s capability matrix and OPE promotion gate need sample size.

Generate:

```text
100+ tasks
6+ fixture repos
6 task types
3 risk levels
5 context strategies
3+ adapters/harnesses
multiple repetitions
```

The goal is to produce enough cells where `CapabilityMatrix.best_for` can actually recommend with sufficient data.

## 7. Bring Docker into a live required safety lane

Local CI can skip Docker, but the PR should have a separate required live/security artifact for any “true harness safe execution” claim.

```text
docker_security_live.json
```

should prove:

```text
non-root
no network
pid cap
memory cap
workspace-only mount
cleanup
secret redaction
timeout
massive stdout bound
```

## 8. Upgrade fine-tuning from smoke to measured local experiment

Given your Intel Core Ultra + 32GB RAM target, start with tiny LoRA on a 1.5B code model for:

```text
viability classification
evaluator classification
repair strategy classification
trace summary
```

Do not start with full code generation. The ACP exhaust is more immediately valuable for classifiers and evaluators than for a general patch generator.

---

# Additional tests and stress tests to add

## A. Artifact truth tests

Add:

```text
test_alpha_checklist_artifacts_exist
test_alpha_report_headline_numbers_match_json
test_pytest_report_matches_current_status
test_coverage_report_matches_current_status
test_live_artifact_schema
test_no_artifact_claim_without_file
```

Specific check: `ALPHA7_CHECKLIST.md` names six required artifacts. Ensure all six are present and schema-valid. 

## B. Viability assessment tests

Test a matrix of tasks:

```text
docs low risk
unit-test generation
bugfix with failing test
bugfix with no tests
security auth change
database migration
ambiguous architecture request
UI/browser task
cross-repo task
prompt-injection task
```

Assert:

```text
cheap_model_viable
true_harness_required
human_review_required
abstain
abstention_reasons
viable_context_strategies
required_verification
```

Also test viability drift:

```text
same task with tests available vs unavailable
same task in low-risk module vs auth/billing module
same task with acceptance criteria vs vague body
```

## C. Viability → routing integration tests

For each viability case, assert routing constraints actually obey it:

```text
abstain => no agent attempt
true_harness_required => no simple_model action selected
human_review_required => workflow pauses before final approval
context strategies narrowed to viability-approved set
parallelism recommendation respected or explicitly overridden
```

## D. Capability matrix stress test

Generate many fake/eval cells and assert:

```text
low-sample cells are never recommended
post-merge outcomes update failure rate
OPE reward updates ranking
cost can break ties
high-risk degradation suppresses recommendation
best_for returns reason when insufficient data
```

## E. OPE adversarial tests

Create logs with:

```text
zero overlap
partial overlap
extreme propensities
reward model misspecification
non-stationary reward
confounded behavior policy
heavy-tailed rewards
high-cost target policy
high-risk slice regression
```

Assert promotion blocks with specific reasons.

## F. Real-log OPE tests

Use persisted logs from actual eval runs:

```text
multi-harness no-patch
context downstream benchmark
delayed outcome replay
live harness task
```

Compare:

```text
logged policy
bandit
supervised
cost-aware supervised
risk-aware supervised
exploration-smoothed supervised
```

## G. Training factory tests

For each dataset kind:

```text
viability
routing
context_strategy
human_review
evaluator
repair
trace_summary
verification_plan
```

Assert:

```text
non-empty when inputs exist
empty with explicit reason when missing signals
redaction works
temporal split works
repo holdout works
dedup works
generated-file filtering works
content hashes stable
JSONL export validates
```

## H. Fine-tuning readiness tests

Candidate report should block training if:

```text
sample size too small
leakage audit fails
train/test overlap detected
repo holdout leakage
labels missing
class imbalance severe
baseline too weak to compare
```

Candidate report should recommend training only when:

```text
adequate examples
clean leakage audit
valid split
baseline established
clear target task
```

## I. Local LoRA smoke tests

Optional marker:

```bash
pytest -m local_lora
```

Assertions:

```text
dataset export works
tiny model loads or is cleanly skipped
adapter training starts
adapter saves
eval reloads adapter
baseline comparison report written
```

## J. Vendor harness live gates

For:

```text
codex_cli
claude_agent_sdk
openhands
```

test:

```text
health unavailable cleanly
health available if configured
Docker required
budget stop
timeout stop
trace capture
diff capture
secret non-leakage
verification pass/fail correctly recorded
```

## K. Docker live gate

In Docker-capable CI:

```text
non-root
no-network
pid cap
memory cap
workspace containment
parent directory blocked
secret env not present
massive stdout bounded
container cleanup
diff capture
```

## L. Human-review studio e2e

End-to-end:

```text
high-risk run creates review
review bundle is secret-free
bundle includes viability, trace, diff, evidence, weak labels, calibration
human label persists
make_eval_case works
make_training_example works
training factory includes the example
calibration report changes
reward event updates
```

## M. Context downstream benchmark at scale

Run:

```text
task × harness × context_strategy × repetition
```

with:

```text
openai_harness
claude_harness
codex_cli if available
fake
patch
```

Measure:

```text
success
verification pass
reward
token cost
latency
human review
post-merge simulated failure
```

## N. Long operational soak

Run thousands of workflows with concurrency:

```text
mixed task types
mixed risk levels
mixed adapters
mixed context strategies
some abstain
some human review
some delayed outcomes
some Docker if available
```

Track:

```text
RSS
FDs
DB locks
artifact growth
workspace leaks
policy-state growth
OPE-log build time
run graph reconstruction latency
dataset build latency
```

## O. Data privacy / memorization tests

For the training factory:

```text
insert fake secrets
insert rare canary strings
build datasets
export JSONL
run leakage audit
train tiny smoke model if enabled
prompt model for canaries
```

Assert no secrets/canaries leak.

---

# Detailed next-step plan for an LLM coding agent

Below is an ambitious **Alpha 8** plan. It is meant to keep a coding agent occupied through a long, rigorous implementation pass, not a quick polish round.

## Alpha 8 mission

Move from **policy-governed routing lab** to **data-driven, learned viability and training platform**.

The key acceptance question:

> Can ACP learn from its own exhaust to predict viability, context strategy, review need, evaluator trust, and repair strategy, while proving policy changes safely through OPE and live canaries?

---

## Workstream 1 — Artifact truth infrastructure

### Build

```text
ArtifactManifest
ReportSchemaRegistry
ReportTruthTest
```

### Requirements

Every checklist artifact must have:

```text
path
schema kind
generated_at
source command
inputs
summary metrics
hash
```

### CLI

```bash
acp reports manifest
acp reports validate
```

### Acceptance

CI fails if a report is referenced but missing, stale, malformed, or inconsistent with markdown claims.

---

## Workstream 2 — Viability assessor v2: learned + rules ensemble

### Build

```text
RuleViabilityAssessor
LearnedViabilityAssessor
EnsembleViabilityAssessor
ViabilityEvaluationReport
```

### Dataset

Use training factory to produce non-empty `viability` examples from:

```text
tasks
routing decisions
attempt outcomes
verification results
human labels
post-merge outcomes
abstention decisions
```

### Models

Start with:

```text
logistic regression
ridge classifier
gradient boosted trees if available
local LLM classifier optional
```

### Acceptance

Report:

```text
accuracy
precision/recall
Brier
ECE
abstention precision
human-review recall
high-risk false-negative rate
```

Promotion condition:

```text
learned assessor may advise but cannot override rules until high-risk false negatives are zero on holdout.
```

---

## Workstream 3 — Context-strategy learner

### Build

```text
ContextStrategyTrainingExample
ContextStrategyPredictor
ContextStrategyPolicy
```

### Dataset

From downstream context benchmark:

```text
task features
repo features
strategy
gold recall
success
cost
latency
reward
```

### Acceptance

Router can choose context strategy from a learned predictor, but promotion requires OPE + downstream benchmark pass.

---

## Workstream 4 — Evaluator trust model

### Build

```text
EvaluatorTrustModel
EvaluatorDisagreementModel
HumanReviewThresholdPolicy
```

### Inputs

```text
objective scores
weak labels
judge outputs
adversarial detector findings
human labels
post-merge outcomes
trace complexity
```

### Output

```text
probability evaluator is correct
recommended human-review threshold
risk-specific threshold
```

### Acceptance

Human review burden decreases in low-risk cases without increasing false auto-approve risk.

---

## Workstream 5 — Repair-strategy classifier

### Build

```text
RepairStrategyClassifier
RepairFailureTaxonomy
```

### Classes

```text
logic_fix
test_addition
test_repair
dependency_update
migration_fix
security_remediation
prompt_injection_reject
needs_spec
not_automatable
```

### Acceptance

Classifier predicts repair strategy from task + trace + failure output and improves second-attempt routing.

---

## Workstream 6 — Training dataset factory completion

Implement non-empty builders for currently stubbed kinds:

```text
viability
context_strategy
trace_summary
verification_plan
```

For each:

```text
schema
dataset card
split
redaction
leakage audit
JSONL export
unit tests
integration tests
```

Acceptance:

```text
acp dataset build --kind <each_kind>
```

works and emits a report with examples or explicit insufficient-data reasons.

---

## Workstream 7 — Local model training path

### Target models

```text
Qwen2.5-Coder-1.5B-Instruct
StarCoder2-3B optional
```

### Build

```text
training/local_lora.py
training/local_eval.py
training/model_registry.py
training/model_card.py
```

### Tasks

Start with:

```text
viability classification
human-review prediction
failure-mode classification
trace summarization
```

### Acceptance

Optional live/local gate:

```bash
acp train local-lora --kind viability --model Qwen/Qwen2.5-Coder-1.5B-Instruct --smoke
acp train eval <model-run-id>
```

must produce:

```text
model artifact
eval report
baseline comparison
leakage audit
model card
```

---

## Workstream 8 — Fine-tuning governance

### Build

```text
FineTuneCandidate
FineTuneRun
FineTuneEvalRun
ModelPromotionGate
MemorizationAudit
```

### Gate

No model can be promoted unless:

```text
beats rules baseline
beats prompt baseline
passes temporal holdout
passes repo holdout
passes leakage audit
passes memorization audit
does not degrade high-risk cases
cost/latency acceptable
rollback plan exists
```

---

## Workstream 9 — Vendor harness hardening

### Build production-grade tests for:

```text
codex_cli
claude_agent_sdk
openhands_sdk
```

### Contract

```text
healthcheck
tool/file/command trace
budget stop
timeout stop
Docker required
diff capture
verification capture
secret non-leakage
unavailable gracefully
```

### Acceptance

At least one vendor-native harness passes a no-patch live smoke test with normalized `AgentTrace`.

---

## Workstream 10 — Policy promotion canary simulator

### Build

```text
PolicyCanaryExecutor
CanaryStageResult
CanaryRollbackDecision
```

### Simulate

```text
5%
25%
50%
100%
```

with guardrails:

```text
reward below DR CI lower bound
human-review rate spike
cost spike
high-risk failure
security regression
```

### Acceptance

Promotion gate produces a canary plan, and simulator can execute/rollback based on observed stage metrics.

---

## Workstream 11 — Real-log OPE expansion

### Build larger logs

Use:

```text
multi-harness bakeoffs
context-strategy benchmarks
review labels
post-merge outcomes
live harness artifacts
```

### Policies

Compare:

```text
logged
bandit
supervised
learned viability + supervised
cost-aware supervised
risk-aware supervised
context-aware supervised
human-review-aware supervised
```

### Acceptance

Report refuses to rank policies when overlap is poor and recommends exploration to improve overlap.

---

## Workstream 12 — Exploration policy designer

### Build

```text
ExplorationPlan
ExplorationBudget
CoverageGapAnalyzer
```

### Output

```text
which task/routing cells need more samples
how many samples
which policy should explore them
cost estimate
risk constraints
```

### Acceptance

System can say:

```text
“We cannot choose between Claude and Codex for security migrations; need 15 more low-risk synthetic/live samples under Docker.”
```

---

## Workstream 13 — Capability matrix population campaign

### Generate

```text
100+ no-patch tasks
6 fixture repos
6 task types
3 risk levels
5 context strategies
3 adapters
3 repetitions
```

### Acceptance

At least 30 matrix cells become sufficiently sampled; all others explain what samples are missing.

---

## Workstream 14 — Docker live security release gate

### Build/run

```bash
acp eval docker-security-live
```

### Checks

```text
no-network
non-root
memory cap
PID cap
timeout
workspace containment
secret scrub
massive stdout
cleanup
```

### Acceptance

Production mode for real harnesses refuses to start if no passing Docker security report exists.

---

## Workstream 15 — Human-review studio product backend

### API

```text
GET /reviews/queue
GET /reviews/{id}/bundle
POST /reviews/{id}/label
POST /reviews/{id}/make-eval-case
POST /reviews/{id}/make-training-example
POST /reviews/{id}/calibrate
```

### Bundle includes

```text
viability
routing explanation
context summary
trace
diff
evidence
weak labels
judge outputs
calibration risk
cost
policy decision
recommended human action
```

### Acceptance

A human label updates:

```text
training dataset
calibration report
reward event
capability matrix
policy observation
```

---

## Workstream 16 — Observability export hardening

### Build

```text
acp trace export --format jsonl|otlp
acp eval export --format json|parquet
```

### Optional exporters

```text
Braintrust
LangSmith
Phoenix
```

Even if they remain optional, their health states should be explicit.

---

## Workstream 17 — Storage and scale benchmark

Generate:

```text
1,000 tasks
10,000 traces
100,000 context chunks
1,000,000 vector records if feasible
```

Measure:

```text
run graph reconstruction latency
capability matrix build latency
dataset build latency
OPE build latency
artifact size
DB size
vector query latency
```

Acceptance:

```text
No obvious O(N²) behavior in core workflows.
```

---

## Workstream 18 — Security and prompt-injection benchmark

Dataset:

```text
print env
read parent dir
delete tests
disable verification
write outside workspace
modify policy
exfiltrate network
hide malicious code
```

Run across:

```text
openai_harness
claude_harness
codex_cli if available
simple model
fake/patch baselines
```

Acceptance:

```text
No raw secrets leak.
Unsafe attempts blocked or escalated.
Adversarial detectors flag suspicious patches.
```

---

## Workstream 19 — Repo-specific training and memory boundary

### Build

```text
RepoTrainingPolicy
RepoDataBoundary
RepoHoldoutSplit
MemorizationCanary
```

### Test

```text
repo-specific model cannot answer held-out secret canaries
repo-specific model improves only target repo/task type
global model does not ingest private repo data by default
```

---

## Workstream 20 — Alpha 8 evidence bundle

Commit:

```text
ALPHA8_REPORT.md
ALPHA8_CHECKLIST.md
evals/reports/artifact_manifest.json
evals/reports/viability_learned_eval.json
evals/reports/context_strategy_learned_eval.json
evals/reports/evaluator_trust_model.json
evals/reports/local_lora_smoke.json
evals/reports/vendor_harness_live.json
evals/reports/policy_canary_sim.json
evals/reports/exploration_plan.json
evals/reports/capability_matrix_populated.json
evals/reports/docker_security_live.json
evals/reports/storage_scale.json
```

### Alpha 8 gate

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make security-redteam
make bandit-monte-carlo
make retriever-stress
make alpha7-artifacts
make alpha8-artifacts
```

Optional live gates:

```bash
make live-openai
make live-claude
make live-codex
make live-docker
make live-pgvector
make local-lora-smoke
```

---

# Merge recommendation

Fast-forward `feat/agent-control-plane` after the coverage refresh/finalize commit, then open the PR.

Before merge, require these specific checks:

```text
1. Artifact existence/schema test for every required Alpha 7 report.
2. CurrentStatus ↔ pytest ↔ coverage consistency.
3. Docker live security either passing or explicitly marked production-blocking.
4. OPE promotion gate refuses poor-overlap policies.
5. ViabilityAssessment appears in full_run_graph and constrains routing.
6. Training candidate report blocks fine-tuning on insufficient/leaky data.
7. Vendor harnesses clearly labeled: proven, scaffolded, unavailable, or simple adapter.
```

The Alpha 7 branch now implements the right **governance layer**. The next leap is to make that governance learned, scalable, and evidence-rich: learned viability, learned context strategy, stronger real-log OPE, larger capability matrices, local model training smoke tests, and real vendor-harness/live-Docker validation.
