## Executive assessment

The current branch has clearly moved beyond the Alpha 7 “policy-governed routing + training pipeline” milestone. I can verify that `feat/agent-control-plane` now contains Alpha 8 artifacts and Alpha 9 source modules, including Pareto routing, drift detection, preference learning, and counterfactual what-if analysis. The repo’s `CURRENT_STATUS.md` still reports Alpha 7 with **498 passing / 7 skipped**, while `ALPHA8_REPORT.md` and the new Alpha 9 files show later work has landed; your sprint note also says the Alpha 9 arc is still progressing and the final suite/count has not yet been committed. So I would treat the current state as:

> **Alpha 8 substantially landed; Alpha 9 partially landed and in progress; docs/test artifacts are not yet fully synchronized.**

The biggest architectural advancement since Alpha 7 is that ACP is no longer only a supervised/OPE-gated router. It is becoming a **multi-objective, continuously monitored decision system**: it can reason over Pareto trade-offs, detect learned-model drift and auto-demote, learn pairwise preferences from human labels, compute per-decision counterfactual regret, and produce control-plane health signals.

This is the right direction. The next level is to wire these modules into the live runner, make their outputs persistent and auditable, and stress them with large, adversarial, multi-objective, multi-harness datasets.

---

# What has been implemented

## 1. Alpha 7 foundation remains intact

The branch still contains the Alpha 7 policy-governed platform: viability assessment, OPE promotion gate, real-log OPE, capability matrix, training-data factory, downstream context benchmark, vendor harness hardening, and review-studio training examples. `CURRENT_STATUS.md` reports Alpha 7 with 498 passing tests, 7 skipped, ruff/mypy clean, and Alembic upgrade in the gate. 

The Alpha 7 report frames the core acceptance question as whether ACP can assess viability, choose agent/model/context/verifier, prove policies offline, run safely, produce training data, and improve a classifier/evaluator from exhaust.  It also states that the OPE promotion gate blocks a deterministic greedy policy for poor overlap while promoting an exploration-smoothed supervised policy with trustworthy diagnostics. 

## 2. Viability assessment is first-class

The `ViabilityAssessment` schema remains one of the most important pieces. It explicitly decides whether and with what resources a task is viable before routing. It narrows viable agent classes and context strategies, records whether cheap models are viable, whether a true harness is required, whether human review is required, and whether the system should abstain. 

The schema includes the right fields: task/risk, ambiguity, testability, evidence, viable agent classes, context strategies, verification requirements, model strength, human review, parallelism, abstention reasons, confidence, and supporting features. 

That is exactly the right abstraction for “which types of request/need are viable with which models and contexts?”

## 3. OPE promotion gate is implemented

`routing/promotion.py` is a strong implementation. It explicitly rejects the idea that a high OPE point estimate is enough to deploy. It requires statistical trust and operational safety. 

The gate checks effective sample size, propensity overlap, max importance weight, DR CI lower bound, SNIPS agreement, cost cap, human-review rate, high-risk degradation, and calibration confidence.  

This is one of the highest-value parts of the system because it prevents “policy looks good offline” from becoming “policy is safe to deploy.”

## 4. Capability matrix exists and is conservative

The capability matrix aggregates evidence per:

```text
task_type × risk_level × repo_type × agent_class × context_strategy × verification_policy
```

It stores success, cost, latency, human-review rate, post-merge failure, OPE reward, calibration confidence, sample size, and update time. 

It also deliberately refuses to recommend low-sample cells. Cells below `MIN_SAMPLE` are flagged `low_sample`, and `best_for` refuses to recommend them. 

This is the right empirical answer to “which harness/context/verifier works best for this kind of task?”

## 5. Alpha 8 learned governance landed

`ALPHA8_REPORT.md` says Alpha 8 makes governance learned and verifiable: it trains models from ACP exhaust to predict viability, context strategy, evaluator trust, and repair strategy, each behind promotion contracts. 

The Alpha 8 report claims these committed artifacts:

```text
learned viability with zero high-risk false negatives on labeled set
context-strategy predictor
evaluator-trust model
repair-strategy classifier
policy canary rollback
directed exploration plan
artifact manifest / acp reports validate
```



It also lists new modules for learned viability, context strategy learning, evaluator trust, repair classification, completed dataset builders, model governance, canary execution, and exploration planning. 

Important caveat: Alpha 8 is honest that these learned models are trained/evaluated on synthetic or small distilled sets, and that real promotion needs more logged traffic. 

## 6. Artifact validation is now part of the system

Alpha 8 adds an artifact-manifest/report-validation layer: 12/12 artifacts at Alpha 8, then a subsequent increment reports 15/15 valid.  

This directly addresses earlier feedback: checklist artifacts should not be prose-only; they should be machine-checkable.

## 7. Pareto routing is now implemented

The new `routing/pareto.py` implements multi-objective Pareto routing over:

```text
success ↑
cost ↓
latency ↓
risk ↓
```

and exposes the non-dominated frontier plus weighted scalarization. 

The module defines an `ObjectiveVector`, dominance, frontier computation, scalarization, `ParetoRouter`, and a helper to construct objectives from capability-matrix cells.  

This is an important conceptual shift. Real routing is not one scalar reward. A high-success/high-cost frontier harness and lower-success/cheap harness can both be correct depending on task risk and budget.

## 8. Drift detection and auto-demotion are implemented

`learning/drift.py` adds a drift loop for promoted learned models. It compares a recent window against a baseline window using accuracy drop, PSI, and recent high-risk false-negative rate, then recommends demotion when drift or high-risk false negatives appear. 

It has a concrete `AutoDemoter` that flips a promoted model back to advisory when drift recommends demotion. 

This is exactly the right safety mechanism for learned viability/evaluator models.

## 9. Preference learning from human labels is implemented

`learning/preference.py` turns human labels into pairwise preferences and fits a Bradley-Terry/logistic-style preference model over attempt features. It can score attempts as learned reward signals for routing/evaluation. 

It builds pairwise preferences from per-attempt human labels and skips attempts with missing features. 

This is a good next step because human labels are often more reliable comparatively than as absolute scalar scores.

## 10. Counterfactual what-if analysis is implemented

`routing/counterfactual.py` answers the per-decision question: for a specific logged decision, what would each alternative action have been expected to yield, and how much regret did the logged choice incur? It reuses the fitted reward model from OPE. 

It exposes `what_if` and `total_regret`, including per-action predicted reward and aggregate regret. 

This complements OPE: OPE evaluates policies; counterfactuals explain individual decisions.

---

# What has not been implemented or is not yet proven

## 1. Alpha 9 is not fully finalized in branch status

The code contains Alpha 9 modules, but `CURRENT_STATUS.md` still says Alpha 7 and reports 498 passing tests.  Your sprint note says Alpha 9 focused tests were being held until the full suite freed up, then the branch would be finalized and fast-forwarded.

So the Alpha 9 code is present, but the release state is incomplete:

```text
no ALPHA9_REPORT.md observed
no ALPHA9_CHECKLIST.md observed
test count not refreshed
coverage not refreshed
Alpha 9 artifact set not yet clearly committed
```

## 2. Pareto routing is not yet wired into live workflow

`pareto.py` is a clean standalone module. I did not see evidence that the live routing node now uses `ParetoRouter` or persists a Pareto frontier per routing decision. The sprint report also says “next: multi-objective routing wired into the runner.”

So current state:

```text
Pareto math: implemented
Pareto integration into runner: not yet complete / not proven
Pareto artifacts: not yet release-gated
```

## 3. Drift detection is not yet clearly connected to real model registry/promotion lifecycle

The drift module can detect and apply demotion, but it appears as a standalone safety module. It still needs to be wired into:

```text
scheduled evaluation windows
promoted model registry
model promotion/demotion audit log
policy rollback/canary plan
review queue
health snapshot
```

## 4. Preference learning is synthetic until real paired human labels exist

The preference model is structurally good, but it needs real human review comparisons. The file includes synthetic defaults for tests/artifacts. 

The key missing data loop is:

```text
multiple attempts per same task
human preference labels across attempts
trace features extracted
preference reward feeds routing
OPE checks whether preference reward improves real outcomes
```

## 5. Counterfactual regret needs uncertainty and overlap diagnostics

The counterfactual module uses a fitted mean reward model and reports predicted reward/regret. 

That is useful, but it should not be treated as ground truth. It needs:

```text
sample count per action
confidence intervals
overlap / support warnings
“insufficient evidence” states
high-risk caution
```

Otherwise, a per-decision “regret” can over-explain sparse data.

## 6. Learned models are still synthetic/small-data

Alpha 8 explicitly says learned models are trained/evaluated on synthetic or small distilled sets and need more logged traffic for real promotion. 

This remains true even as Alpha 9 adds Pareto/drift/preference modules.

## 7. Docker live-security and vendor-native live proof remain open

Alpha 8 lists Docker live-security gate and vendor-native live smoke as deferred. 

Given the product’s safety posture, this is still a release blocker for running untrusted real agents in production-like settings.

## 8. Control-plane health snapshot is reported but not verified in fetched code

Your sprint note says `AppService.control_plane_health` and `acp health` now unify counts, OPE readiness, learned-model promotability, and counterfactual regret. I did not fetch the implementation successfully, so I would treat it as reported but not independently verified.

---

# Constructive feedback

## 1. Promote Alpha 9 around “decision quality,” not more features

Alpha 9 should be framed as:

> **Decision-quality layer: multi-objective routing, drift-safe learned models, preference-derived rewards, per-decision counterfactual regret, and control-plane health.**

That is a coherent story.

## 2. Wire Pareto routing into the live runner before adding more decision modules

Right now, Pareto routing is likely standalone. The next milestone should persist this per decision:

```text
candidate objective vectors
non-dominated frontier
chosen weight profile
chosen frontier point
dominated candidates
scalarization score
reason
```

Then include it in:

```text
run graph
review bundle
policy OPE logs
counterfactual analysis
control-plane health
```

## 3. Use Pareto routing to expose product trade-offs

Do not reduce Pareto back to “one best.” Make the UI/API explain:

```text
cost-minimizing choice
success-maximizing choice
low-risk choice
balanced choice
chosen choice
why chosen
what trade-off was accepted
```

This is a powerful product differentiator.

## 4. Make drift detection automatically demote, but never silently

Every auto-demotion should produce:

```text
DriftReport
AuditEvent
ModelDemotionEvent
Review item if high-risk false negatives caused demotion
policy rollback event
```

The system should answer:

```text
Which model was demoted?
Why?
Which recent cases caused it?
What policy replaced it?
What human review is needed?
```

## 5. Treat preference learning as reward-model v0, not truth

Pairwise human preference is a strong signal, but it can encode reviewer bias and local style preferences. Route with it only after:

```text
reviewer agreement measured
preference model calibrated
task/risk slices evaluated
objective-regression guardrails applied
post-merge outcomes checked
```

## 6. Unify OPE, Pareto, preference, and counterfactual under one policy report

A policy report should include:

```text
OPE value estimate
Pareto frontier effects
counterfactual regret
preference reward impact
drift status
capability-matrix sample coverage
promotion-gate decision
canary plan
```

Right now, these modules are separate. The next product win is a single “Policy Decision Dossier.”

## 7. Make Alpha 9 artifact-first

Before continuing the arc indefinitely, cut an Alpha 9 checkpoint:

```text
ALPHA9_REPORT.md
ALPHA9_CHECKLIST.md
reports/pytest.txt refreshed
reports/coverage.txt refreshed
evals/reports/pareto_routing.json
evals/reports/drift_demote.json
evals/reports/preference_learning.json
evals/reports/counterfactual_regret.json
evals/reports/control_plane_health.json
```

This keeps the project reviewable.

---

# Tests to add beyond current suite

## A. Pareto routing tests

Add tests for:

```text
dominance correctness
ties / equal objective vectors
all candidates dominated except one
no candidates
single candidate
NaN/None/negative values rejected or normalized
cost-heavy weights choose cheap frontier point
success-heavy weights choose high-success frontier point
risk-heavy weights avoid high post-merge failure
frontier preserved in original order
```

Integration tests:

```text
routing decision persists frontier
run graph includes Pareto explanation
review bundle includes trade-offs
policy report includes chosen weight profile
```

## B. Pareto stress test

Generate 10,000 synthetic capability cells with correlated objectives:

```text
success vs cost
latency vs cost
risk vs success
```

Assert:

```text
frontier computed under latency budget
frontier size reasonable
no O(N²) problem for expected production sizes or optimized path added
```

Current `pareto_frontier` is simple O(N²), which is fine for small candidate sets but should be tested at the scale of capability-matrix cells. 

## C. Pareto + OPE consistency tests

For each target policy:

```text
balanced
cost-minimizing
success-maximizing
risk-minimizing
```

Run OPE and verify:

```text
promotion gate passes/fails appropriately
cost-minimizing policy reduces cost
success-maximizing policy increases success but may fail cost cap
risk-minimizing policy improves high-risk slice
```

## D. Drift detection tests

Beyond current unit tests, add:

```text
gradual drift
sudden drift
label delay
seasonality
small recent window
no high-risk cases
one high-risk false negative
PSI high but accuracy stable
accuracy drop but PSI low
drift followed by recovery
```

Integration tests:

```text
drift report persisted
model demoted
audit event persisted
policy promotion status changes
review item created for high-risk false negative
```

## E. Preference learning tests

Add realistic cases:

```text
multiple reviewers
reviewer disagreement
ties / uncertain labels
partial verdicts
high objective pass but poor human preference
human preference conflicts with post-merge outcome
preference model trained on one task type and tested on another
```

Gate promotion on:

```text
pairwise accuracy
calibration
reviewer agreement
post-merge agreement
high-risk non-degradation
```

## F. Counterfactual tests

Add:

```text
unsupported action => insufficient support warning
low sample action => wide CI
zero overlap => no regret claim
conflicting reward model => uncertainty
counterfactual explanation appears in run graph
```

The current counterfactual module returns point-estimate regret; add confidence/support metadata before exposing it in UI. 

## G. Control-plane health snapshot tests

The health snapshot should assert:

```text
artifact manifest valid
test count fresh
coverage fresh
OPE logs enough overlap
capability matrix sufficient cells
learned models promotable/advisory/demoted
drift status
counterfactual regret mean/max
Docker live gate status
vendor harness live status
training data readiness
```

## H. End-to-end policy dossier test

Given a new candidate policy, produce:

```text
OPE report
promotion decision
Pareto frontier report
counterfactual regret report
preference reward report
drift status
canary plan
```

Assert all IDs link back to persisted data.

## I. Active-learning exploration tests

Implement and test the next reported target:

```text
find under-sampled capability cells
choose exploration tasks/actions
respect cost/risk budgets
avoid high-risk exploration without human approval
improve OPE overlap after simulated exploration
```

## J. Continuous-learning scheduler tests

Add a scheduler that runs:

```text
nightly dataset build
weekly OPE
drift detection
capability matrix refresh
artifact validation
exploration plan
training candidate report
```

Test idempotency, partial failures, and stale report alerts.

## K. Multi-objective runner integration tests

When Pareto routing is wired into the runner:

```text
same task under cost-heavy profile chooses cheaper action
same task under success-heavy profile chooses stronger harness
high-risk task profile prioritizes risk
chosen action still satisfies ViabilityAssessment
OPE logs include objective vectors
```

## L. Real-data stress run

Run:

```text
500–1,000 no-patch tasks
multiple fixtures
multiple task types
multiple context strategies
multiple adapters
some human labels
some post-merge outcomes
```

Measure:

```text
OPE overlap
capability matrix coverage
Pareto frontier size
counterfactual regret
preference model accuracy
drift false alarms
scheduler latency
storage growth
```

---

# Detailed next-step plan for an LLM coding agent

Below is a larger, more strenuous Alpha 9/10 plan. It assumes the coding agent will keep working continuously, run full gates, commit artifacts, and keep `IMPLEMENTATION_LOG.md` updated.

## Alpha 9 completion mission

Turn the currently in-progress Alpha 9 arc into a **reviewable release checkpoint**.

### Workstream 1 — Finalize Alpha 9 reports and status

Create:

```text
ALPHA9_REPORT.md
ALPHA9_CHECKLIST.md
evals/reports/pareto_routing.json
evals/reports/drift_demote.json
evals/reports/preference_learning.json
evals/reports/counterfactual_regret.json
evals/reports/control_plane_health.json
reports/pytest.txt
reports/coverage.txt
```

Update:

```text
CURRENT_STATUS.md
docs/status_schema.md if needed
Makefile alpha9-artifacts
```

Acceptance:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha9-artifacts
acp reports validate
```

## Workstream 2 — Wire Pareto routing into live runner

Implement:

```text
ParetoRoutingPolicy
ParetoWeightProfile
ParetoDecisionExplanation
```

Persist in `RoutingDecision.metadata` or new schema:

```text
objective_vectors
frontier
chosen_weight_profile
dominated_count
chosen_score
tradeoff_summary
```

Add CLI:

```bash
acp policy pareto-report
acp run explain-route <run-id>
```

Acceptance:

```text
Pareto explanation appears in full_run_graph and review bundle.
```

## Workstream 3 — Multi-objective policy profiles

Add profiles:

```text
cost_saver
balanced
success_max
risk_min
latency_min
human_review_min
```

Each profile must define:

```text
weights
hard constraints
allowed risk levels
minimum success estimate
cost ceiling
human review policy
```

Acceptance:

```text
Same candidate set produces different rational choices under different profiles.
```

## Workstream 4 — Pareto + OPE integration

For each profile, create target policy and evaluate:

```text
cost_saver under OPE
balanced under OPE
success_max under OPE
risk_min under OPE
```

Promotion gate must include:

```text
DR/SNIPS
ESS
overlap
cost delta
high-risk delta
human-review delta
```

Acceptance:

```text
Policies with bad overlap or unacceptable cost/risk trade-off are blocked.
```

## Workstream 5 — Drift lifecycle integration

Add entities:

```text
DriftReportEntity
ModelDemotionEvent
ModelPromotionState
```

Wire:

```text
nightly drift detector
auto-demote
audit event
policy rollback
review item for high-risk false negative
```

Acceptance:

```text
A simulated high-risk false negative demotes a promoted learned model and creates a review item.
```

## Workstream 6 — Preference reward integration

Add:

```text
PreferenceDatasetBuilder
PreferenceRewardModel
PreferenceRewardEvent
```

Use preference reward alongside objective reward:

```text
combined_reward = objective_reward + preference_weight * preference_reward
```

But gate it behind:

```text
reviewer agreement
pairwise accuracy
post-merge correlation
high-risk non-degradation
```

Acceptance:

```text
Preference model affects routing only after passing gate.
```

## Workstream 7 — Counterfactual decision dossier

For every completed run, optionally compute:

```text
best alternative
logged choice predicted reward
regret
support count per alternative
insufficient-support warnings
```

Add to:

```text
run graph
review bundle
policy dossier
control-plane health
```

Acceptance:

```text
Counterfactual regret is hidden or marked untrusted when sample support is too low.
```

## Workstream 8 — Control-plane health snapshot

Implement/finish:

```text
AppService.control_plane_health
acp health
GET /health/control-plane
```

Include:

```text
test/artifact freshness
OPE readiness
policy promotion state
drift state
learned model state
capability matrix coverage
Pareto profile status
counterfactual regret
Docker security status
vendor harness status
training readiness
storage health
```

Acceptance:

```text
Health snapshot exits nonzero or reports degraded when critical gates are stale/missing.
```

## Workstream 9 — Active-learning exploration executor

Implement:

```text
ExplorationExecutor
ExplorationTaskGenerator
ExplorationBudgetPolicy
```

Inputs:

```text
capability matrix low-sample cells
OPE poor-overlap diagnostics
counterfactual high-regret decisions
drift uncertain windows
```

Outputs:

```text
recommended task/adapters/context strategies
expected cost
risk constraints
sample-size target
```

Acceptance:

```text
After simulated exploration, capability-matrix coverage and OPE overlap improve.
```

## Workstream 10 — Continuous-learning scheduler

Implement:

```text
ContinuousLearningScheduler
ScheduledJobState
JobRunReport
```

Jobs:

```text
artifact validation
dataset build
capability matrix refresh
OPE refresh
promotion check
drift detection
exploration planning
training candidate report
health snapshot
```

Acceptance:

```text
Scheduler is idempotent, resumable, and produces reports even on partial failures.
```

---

# Alpha 10 mission: scale and production-lab hardening

Once Alpha 9 is finalized, Alpha 10 should be much more operational and scale-focused.

## Workstream 11 — Large empirical corpus

Generate:

```text
1,000+ no-patch tasks
10 fixture repos
6 task types
3 risk levels
5 context strategies
4 adapters/harnesses
3 repetitions
```

Targets:

```text
>500 sufficient capability cells
meaningful OPE overlap
non-trivial Pareto frontiers
preference dataset >1,000 pairs
```

## Workstream 12 — Real Docker security gate

Run in Docker-capable CI and commit:

```text
evals/reports/docker_security_live.json
```

Checks:

```text
no network
non-root
memory cap
PID cap
timeout
workspace containment
secret scrub
massive stdout bound
cleanup
```

Production mode should refuse true harness runs without a fresh passing Docker report.

## Workstream 13 — Vendor harness live campaign

For:

```text
codex_cli
claude_agent_sdk
openhands if feasible
```

Run:

```text
health
no-patch bugfix
budget stop
timeout stop
trace capture
diff capture
verification
secret non-leakage
Docker enforcement
```

Commit:

```text
evals/reports/vendor_harness_live.json
```

## Workstream 14 — Real preference-learning campaign

Create a review-label simulator plus optional real review UI flow:

```text
two attempts per task
human preference labels
reviewer disagreement
tie/uncertain labels
post-merge outcomes
```

Evaluate:

```text
pairwise accuracy
calibration
reviewer agreement
post-merge correlation
routing improvement under OPE
```

## Workstream 15 — Learned viability promotion campaign

Take learned viability from advisory to canary-authoritative only if:

```text
zero high-risk false negatives on temporal holdout
zero high-risk false negatives on repo holdout
drift monitor clean
human-review false-negative rate acceptable
abstention precision acceptable
```

Then run canary simulation:

```text
5% → 25% → 50% → 100%
```

## Workstream 16 — Local LoRA training experiment

Use the training factory to run a real local smoke experiment:

```text
Qwen2.5-Coder-1.5B-Instruct
dataset: viability or evaluator
LoRA adapter
baseline vs fine-tuned
memorization audit
repo holdout
temporal holdout
model card
```

Commit:

```text
evals/reports/local_lora_viability.json
```

Do not require this in default CI.

## Workstream 17 — Storage and performance benchmark

Run scale benchmark:

```text
10k tasks
100k traces
1M context chunks if feasible
```

Measure:

```text
run graph reconstruction
capability matrix build
OPE build
dataset build
context retrieval
artifact validation
health snapshot
```

Add indexes or query optimizations where needed.

## Workstream 18 — Security/prompt-injection v2

Expand attacks:

```text
prompt asks to exfiltrate secrets
disable tests
delete tests
modify policy
hide malicious code
write outside workspace
network exfiltration
supply-chain mutation
poison training data
poison reward model
```

Run against:

```text
simple model
openai_harness
claude_harness
codex_cli
```

## Workstream 19 — Model/data governance

Add:

```text
DatasetAccessPolicy
RepoDataBoundary
ModelTrainingPermission
MemorizationCanary
ModelRollbackPolicy
```

Acceptance:

```text
No private repo data enters global datasets without explicit policy.
```

## Workstream 20 — Alpha 10 release bundle

Commit:

```text
ALPHA10_REPORT.md
ALPHA10_CHECKLIST.md
evals/reports/large_empirical_corpus.json
evals/reports/docker_security_live.json
evals/reports/vendor_harness_live.json
evals/reports/preference_campaign.json
evals/reports/learned_viability_canary.json
evals/reports/local_lora_viability.json
evals/reports/storage_scale_v2.json
evals/reports/security_injection_v2.json
evals/reports/control_plane_health.json
```

Gate:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha9-artifacts
make alpha10-artifacts
acp reports validate
acp health
```

---

# Merge recommendation

I would not merge the in-progress Alpha 9 arc until the release checkpoint is cut.

Before merge:

```text
1. Finish full suite.
2. Refresh reports/pytest.txt and reports/coverage.txt.
3. Add ALPHA9_REPORT.md and ALPHA9_CHECKLIST.md.
4. Commit Pareto/drift/preference/counterfactual/health artifacts.
5. Fast-forward feat/agent-control-plane.
6. Run acp reports validate.
```

The Alpha 9 direction is excellent. It adds the missing decision-quality layer: multi-objective trade-offs, drift-safe learned models, human preference rewards, counterfactual explanations, and health snapshots. The next step is not more standalone modules; it is wiring them into the live runner, policy promotion flow, review bundle, and continuous-learning scheduler so the system can not only **choose** but also **explain, monitor, demote, and improve** those choices.
