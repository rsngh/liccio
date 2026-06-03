## Executive assessment

The current `feat/agent-control-plane` branch has reached a strong **Alpha 10 / preproduction-lab** checkpoint. It now implements the original architecture at meaningful depth: durable agent execution, context compilation, multi-harness routing, evaluation/verification, human feedback, offline policy evaluation, capability matrices, learned governance, Pareto routing, drift demotion, preference learning, active learning, continuous scheduling, scale benchmarks, and data-governance controls.

The latest committed status reports:

```text
670 passed
9 skipped
ruff clean
mypy clean across 192 source files
Alembic upgrade head OK
```



The project is still correctly labeled as **local v0 / alpha, not production-grade**, with external harnesses, container isolation, and managed backends still optional or partially stubbed.  That caveat remains important. The branch is now impressive, but production readiness depends on live Docker/Kubernetes security, vendor harness campaigns, and real-world data volume rather than synthetic/fixture evidence alone.

Your sprint report says a recent live OpenAI/Anthropic bakeoff exposed several measurement bugs—missing Claude harness due to cached settings, timeout artifacts, cost-blind routing, OpenAI tool activation failure, and infra timeouts being misclassified as task failures. That is a very good sign. The system is starting to discover and correct its own measurement flaws, which is exactly what an empirical routing lab should do.

---

# What has been implemented

## 1. Core control-plane architecture

The original plan called for an independent agent harness that routes, runs, verifies, evaluates, learns, and improves. The current branch now implements that core loop:

```text
task → context → route → attempt → verify → evaluate → human → reward → learn
```

`CURRENT_STATUS.md` describes it as a durable 16-node `WorkflowRunner`, with persistence, resume, full provenance, adaptive routing, evaluation ladder, command execution, context compiler, verification, observability, post-merge loop, API/CLI, and long evals. 

That is the backbone of the original product thesis.

## 2. Multi-harness empirical routing

The repo has two ACP-native true tool-loop harnesses:

```text
openai_harness
claude_harness
```

It also has normalized `AgentTrace`, a multi-harness no-patch bakeoff, routing from those bakeoffs, and evaluator calibration. 

Your latest sprint report adds that real OpenAI + Anthropic harnesses were run on no-patch git tasks, verified by each repo’s own pytest, and that the resulting measurements corrected several earlier routing beliefs. The most important empirical result is that **gpt-4o-mini appears competitive across tested tasks at much lower cost, while Claude Haiku keeps an edge on bugfix and test generation**. I would treat that as a useful current empirical hypothesis, not a final result, until it is repeated over larger corpora.

## 3. Viability assessment

The repo now has a first-class `ViabilityAssessment` primitive. It decides whether a request is viable, whether a cheap model can handle it, whether a true harness is required, which context strategies are viable, whether human review is required, and whether the system should abstain. 

The schema includes task/risk, ambiguity, testability, evidence, viable agent classes, context strategies, verification requirements, model strength, human review, parallelism, abstention, confidence, and supporting features. 

This is a major implementation of the “what kinds of request are viable with what model/context?” idea.

## 4. Capability matrix

The capability matrix aggregates empirical evidence by routing cell:

```text
task_type × risk_level × repo_type × agent_class × context_strategy × verification_policy
```

with success, cost, latency, human-review rate, post-merge failure, OPE reward, calibration confidence, sample size, and last updated. 

It explicitly refuses to recommend under-sampled cells, marking them low-sample and requiring enough evidence before recommendation. 

Alpha 10 reports a large empirical corpus with **930 sufficiently sampled capability cells** and **1,740 preference pairs**, which is a meaningful lab-scale evidence base. 

## 5. Offline policy evaluation and promotion gating

The repo has an OPE-based policy-promotion gate. It blocks policies that look good on point estimates but have poor statistical support. It checks effective sample size, propensity overlap, max importance weight, doubly robust confidence bounds, SNIPS agreement, cost caps, human-review caps, high-risk degradation, and calibration confidence.  

This is one of the strongest parts of the system. It prevents an unsafe router from being promoted merely because a logged dataset flatters it.

## 6. Learned governance and lightweight ML

The repo has real **classical/statistical ML**, not just handwaving:

```text
learned viability
context-strategy prediction
supervised meta-router
preference scoring
evaluator-trust modeling
repair-strategy classification
bandit/OPE/statistical routing
drift detection
counterfactual regret
```

It does **not** run PyTorch model training by default. The project dependencies include optional `scikit-learn`, but not default `torch`; the local LoRA module explicitly imports cleanly without `torch`, `peft`, or `transformers`, and full LoRA training is not wired.   

So the honest description is:

> **Real lightweight ML/statistical decision learning: yes. PyTorch/fine-tuned neural models: scaffolded, not operational.**

## 7. Learned viability and safety contract

The learned viability assessor is built around a good safety design: learned viability may advise but cannot override safety decisions—abstain, true-harness requirement, human review—until it has zero high-risk false negatives on holdout. 

This is the right model-governance posture.

## 8. Context-strategy learning

The context-strategy predictor learns expected reward over task type, risk level, and context strategy, then ranks strategies. It remains explicitly subject to OPE and downstream benchmark promotion before live routing. 

That addresses a key original premise: **context choice is part of routing**, not just model choice.

## 9. Pareto routing

Alpha 9/10 adds multi-objective Pareto routing across:

```text
success ↑
cost ↓
latency ↓
risk ↓
```

The Pareto module computes non-dominated candidates and chooses from the frontier using weight profiles. 

`CURRENT_STATUS.md` says there is now a Pareto routing policy with six profiles:

```text
cost_saver
balanced
success_max
risk_min
latency_min
human_review_min
```



This is an important product feature. There is no single “best” agent; the right agent depends on cost, latency, risk, and success objective.

## 10. Drift detection and auto-demotion

Drift detection watches promoted learned models for accuracy drop, PSI shift, and recent high-risk false negatives. It can demote a learned model back to advisory. 

The implementation includes `AutoDemoter`, which flips `learned_promoted` back to `False` when demotion is recommended. 

This is critical if learned components are ever used in production-like decision paths.

## 11. Preference learning

The repo can derive pairwise preferences from human labels and fit a preference scorer. 

This is useful, especially given the research lesson that relative trajectory evaluation is often more informative than final answer scores alone. AgensFlow similarly argues that agentic systems should be evaluated through relative trajectory comparisons and reward audit, not only final outputs. 

## 12. Counterfactual regret

The repo implements per-decision counterfactual what-if analysis: what would alternative actions likely have yielded, and how much regret did the logged choice incur? 

This is a strong explainability primitive for router improvement.

## 13. Active learning, scheduler, and health

Alpha 9 adds active-learning exploration, a continuous-learning scheduler, and unified `acp health`. The checklist says active learning turns capability-matrix gaps into budget/risk-bounded probes, and the scheduler runs an idempotent, fault-tolerant job batch. 

That moves ACP from “run evaluations manually” toward an autonomous experimentation/control loop.

## 14. Scale and security hardening

Alpha 10 adds:

```text
large empirical corpus
storage/performance benchmark v2
security/prompt-injection benchmark v2
model/data governance
```

The report says the scale benchmark is sub-quadratic, the security benchmark covers 10 attack classes with zero planted-secret leakage, and governance blocks private-repo data from global training without allowlist. 

This is a meaningful hardening milestone.

---

# What has not been implemented or remains insufficiently proven

## 1. Live Docker/security gate still not proven in committed default evidence

Alpha 10 explicitly says Docker live-security is environment-gated and skipped when Docker is unavailable.  The test report also says Docker workspace tests are among the skipped tests. 

For production-like use, this is a blocker. The local runner is not an OS-level sandbox.

## 2. Vendor-native harness campaigns remain environment-gated

The repo has ACP-native OpenAI/Claude harnesses and vendor scaffolding, but live Codex/SDK-style evidence is still skipped. 

The original product is strongest when ACP can compare real coding agents such as Codex CLI/SDK, Claude Code/Agent SDK, OpenHands, Aider, Cline/Roo, etc. That is not yet proven at scale.

## 3. Fine-tuning is not operational

The training-data pipeline is now substantial, but actual PyTorch/LoRA training is not active. The LoRA module says the heavy dependencies are optional and that full local LoRA training is not wired in the scaffold. 

This is fine for now, but the repo should not overclaim fine-tuning.

## 4. Coverage artifact is stale

The pytest report is Round 10 current, but `reports/coverage.txt` is still labeled Alpha 6. 

This is a trust issue, not a technical architecture issue. Refresh it.

## 5. Synthetic and fixture artifacts still dominate

Alpha 9 explicitly says the Pareto/drift/preference machinery is real, but many artifacts use synthetic/deterministic data and become richer only with larger corpus/live campaigns. 

The system has the machinery; it still needs more live and semi-live evidence.

## 6. Harness activation/adherence metrics are only partially addressed

Your latest sprint report says WS6, HAR/HFR/PWL, completed. That is exactly the right response to the harness-benefit paper. However, I would still verify whether these metrics are:

```text
persisted
included in AgentTrace or run graph
included in capability matrix
included in routing features
included in health reports
available by model/harness/task type
```

The harness-benefit paper’s key point is that weak models fail in two separable ways: they fail to activate harness artifacts, or they load them but fail to follow them.  These metrics should become first-class routing features.

## 7. Harness evolution is still not a full PR-like pipeline

ACP has learned governance and training-data factories, but it does not yet clearly implement a full harness update pipeline:

```text
HarnessUpdateProposal
HarnessDiff
Regression tests
Negative-transfer tests
Security scan
Human review
Canary
Rollback
```

The harness-evolution paper warns that persistent harness updates can carry unsafe instructions, incorrect lessons, or sensitive data into future tasks.  ACP should treat harness updates like code changes.

## 8. Topology learning is still less mature than model/context routing

AgensFlow emphasizes topology as a learnable action surface, especially `skip:X`, where the policy learns when to omit retrieval, verification, or other costly cells. 

ACP has Pareto routing, context routing, viability, and active learning, but topology-skip learning should become a more explicit action class.

---

# Constructive feedback

## 1. Treat the latest live bakeoff as a pivotal product lesson

Your session report is exactly the right empirical loop:

```text
measurement → surprising artifact → diagnosis → fix → remeasure
```

The important findings were not just “OpenAI cheaper” or “Claude better at test generation.” The important findings were:

```text
cached settings can hide a harness
provider default retries break wall-time budget
timeouts can masquerade as model quality
tool activation bugs can look like model weakness
infra hangs can poison the capability matrix
cost-blind routing disagrees with product value
```

These should be codified into tests and metrics.

## 2. Make “measurement hygiene” a first-class module

Add:

```text
MeasurementHygieneReport
InfrastructureFailureClassifier
ProviderRetryAudit
TimeoutAttribution
HarnessAvailabilityAudit
ToolActivationAudit
```

This would prevent future false conclusions like “Claude dominates security” when the signal is actually timeout behavior.

## 3. Persist real live cells into the production capability matrix

Your report says the natural next step is persisting real cells into production routing/health. I agree. The current empirical live result should become:

```text
CapabilityCell
EvalRun
AgentTrace
HarnessMetrics
CostMetrics
TimeoutAttribution
MeasurementQualityFlag
```

Then the matrix can route from real evidence, not just artifact summaries.

## 4. Make infra failures non-poisoning by default

Every attempt should be classified:

```text
solved
failed_task
failed_verification
failed_harness_activation
failed_timeout_provider
failed_timeout_agent
failed_infra
inconclusive
```

Only task-relevant failures should update model quality. Infra/inconclusive failures should update reliability/availability metrics, not solve-rate.

## 5. Make cost a first-class tie-breaker everywhere

Your report says cost-blind routing was fixed with matrix cost tie-break and cost-aware OPE. That should be applied consistently:

```text
CapabilityMatrix.best_for
Pareto routing
OPE promotion
counterfactual regret
human review bundle
health report
```

## 6. Add provider-specific timeout/retry policy

The 607s / 241s vs 120s budget finding is important. Provider SDK defaults can silently violate ACP’s budget model. Make all providers pass through:

```text
per-call timeout
max_retries=0 unless explicitly allowed
wall-clock budget supervisor
provider retry attribution
budget ledger event
```

## 7. Make tool activation a harness-benefit metric

The OpenAI test_generation jump after `tool_choice="required"` is a harness activation bug, not a model-quality bug. Track:

```text
tool_required
tool_offered
tool_called
tool_call_valid
first_tool_call_latency
tool_activation_failure
```

This maps directly to HAR/HFR/PWL.

---

# Additional tests and stress tests to run

## A. Harness availability test

Simulate cached settings and dynamic env changes:

```text
OPENAI_API_KEY present/absent
ANTHROPIC_API_KEY present/absent
settings cached before env set
settings reset
adapter registry rebuild
```

Assert:

```text
both harnesses appear when keys exist
missing harness is reported as unavailable, not silently absent
health degrades if expected harness absent
```

## B. Provider timeout and retry test

For each provider adapter:

```text
per-call timeout respected
max_retries=0 by default
wall-time budget respected
provider internal retry disabled
long first call classified infra timeout if no tool call
timeout does not become model-quality failure
```

## C. Inconclusive/infra failure classification test

Create attempts that:

```text
timeout before first tool call
timeout after solving
provider 429
provider 500
network failure
verification command timeout
harness process hang
```

Assert:

```text
matrix quality not poisoned
availability/reliability metrics updated
solved-despite-hang retained as solved + infra warning
inconclusive excluded from success denominator
```

## D. Tool activation regression test

For OpenAI/Anthropic harnesses:

```text
tool_choice required
tool_choice auto
tool schema malformed
tool schema valid
model refuses tool
model calls wrong tool
```

Assert activation metrics reflect the outcome.

## E. Cost-aware routing consistency test

For the same capability matrix:

```text
CapabilityMatrix.best_for
ParetoRouter cost_saver
OPE target policy
Counterfactual best action
Control-plane health recommendation
```

should agree under a cost-aware objective.

## F. Live no-patch corpus expansion

Run live/semi-live:

```text
bugfix
test_generation
security
migration
refactor
CI failure
```

Across:

```text
gpt-4o-mini via openai_harness
claude-haiku via claude_harness
codex_cli if available
```

Require:

```text
repo pytest verification
per-call timeout
zero hidden retries
cost logging
HAR/HFR/PWL
inconclusive classification
```

## G. Measurement mutation test

Deliberately break measurement:

```text
disable Claude env after registry init
turn on provider retries
remove tool_choice required
force verification timeout
inject fake provider 500s
```

Assert ACP detects the measurement flaw.

## H. Capability matrix non-poisoning test

Feed:

```text
5 true failures
5 infra failures
5 successes
5 solved-despite-timeout
5 inconclusive
```

Assert:

```text
success_rate only uses conclusive task outcomes
reliability_rate tracks infra
cost includes all billable attempts
recommendation explains excluded samples
```

## I. Harness benefit metrics test

For each harness:

```text
HAR: relevant harness/tool loaded
HFR: harness followed
PWL/PWHL: pass when loaded
activation failure
adherence failure
```

Assert those metrics enter:

```text
AgentTrace
CapabilityCell
PolicyDossier
HealthSnapshot
```

## J. Long live soak with provider budgets

Run controlled live soak with hard caps:

```text
N tasks
max total spend
max per provider spend
max wall-clock per task
max retries 0
```

Assert spend never exceeds budget and failures are classified correctly.

---

# Detailed next-step plan for an LLM coding agent

Below is a deliberately ambitious Alpha 11/12 plan focused on the new live-measurement findings.

## Alpha 11 mission

Turn ACP from a powerful empirical lab into a **measurement-trustworthy live routing system**.

The key acceptance question:

> Can ACP run real harnesses, classify infrastructure vs model failures correctly, enforce cost/time budgets, persist clean evidence, and update routing only from trustworthy conclusive outcomes?

---

## Workstream 1 — Measurement hygiene layer

### Build

```text
MeasurementHygieneReport
AttemptOutcomeClassifier
InfrastructureFailureKind
ProviderCallAudit
MeasurementQualityFlag
```

### Classify

```text
task_success
task_failure
verification_failure
harness_activation_failure
harness_adherence_failure
infra_timeout_before_action
infra_timeout_after_solution
provider_rate_limit
provider_server_error
provider_retry_exceeded
inconclusive
```

### Acceptance

Capability matrix and OPE use only conclusive task-quality outcomes for solve rate, while infra failures feed reliability metrics.

---

## Workstream 2 — Provider budget enforcement

### Build

```text
ProviderPolicy
ProviderCallBudget
ProviderRetryPolicy
ProviderTimeoutPolicy
```

### Requirements

```text
per-call timeout
wall-clock budget
max_retries default 0
provider retry audit
hard stop on budget
budget ledger event
```

### Tests

```text
OpenAI respects per-call timeout
Anthropic respects per-call timeout
provider retry disabled by default
wall-clock cap wins over provider behavior
timeout attribution correct
```

---

## Workstream 3 — Harness availability and settings invalidation

### Build

```text
HarnessAvailabilityAudit
SettingsCacheReset
AdapterRegistryRefresh
```

### Tests

```text
env key appears after settings load
env key disappears after registry build
expected harness absent
health degraded
registry refresh fixes it
```

### Acceptance

A harness can never be silently absent.

---

## Workstream 4 — Tool activation metrics

### Add to `AgentTrace`

```text
tools_offered
tools_required
tool_calls_valid
first_tool_call_turn
activation_failure_reason
tool_choice_mode
```

### Metrics

```text
ToolActivationRate
ToolValidityRate
FirstToolLatency
ToolChoiceSensitivity
```

### Acceptance

The OpenAI `tool_choice="required"` bug would have been visible as an activation failure.

---

## Workstream 5 — Harness adherence metrics

### Add

```text
HarnessActivationRate
HarnessFollowingRate
PassWhenLoaded
AdherenceDecay
ActivationFailureReason
AdherenceFailureReason
```

### Integrate into

```text
AgentTrace
CapabilityMatrix
PolicyDossier
HealthSnapshot
```

### Acceptance

Routing can prefer a model with lower raw capability but higher harness adherence when appropriate.

---

## Workstream 6 — Capability matrix v2

### Add fields

```text
conclusive_sample_size
inconclusive_sample_size
infra_failure_rate
provider_failure_rate
harness_activation_rate
harness_following_rate
pass_when_loaded
cost_per_conclusive_success
```

### Recommendation logic

```text
use conclusive success
penalize infra/reliability separately
cost tiebreak
no-overclaim on thin samples
```

### Acceptance

Timeout artifacts cannot create false “Claude dominates” conclusions.

---

## Workstream 7 — Cost-aware OPE v2

### Add

```text
reward_cost_weight
expected_cost
cost_per_success
provider_cost_model
```

### Tests

```text
high-success high-cost policy blocked under cost_saver
low-cost equal-quality policy promoted
cost cap enforced in promotion gate
counterfactual regret includes cost-adjusted regret
```

---

## Workstream 8 — Live cell persistence

### Build

```text
LiveEvalRun
LiveCapabilityCellIngest
LiveMeasurementArtifact
```

### Ingest

```text
live OpenAI/Claude no-patch tasks
pytest verification
cost
latency
HAR/HFR/PWL
timeout attribution
excluded inconclusive rows
```

### Acceptance

Real cells affect `acp viability matrix` and `acp health`.

---

## Workstream 9 — Policy dossier v2

### Add measurement section

```text
measurement quality
excluded samples
infra failures
provider reliability
tool activation
harness adherence
cost sensitivity
```

### Acceptance

Reviewer can see whether a recommendation is based on clean task outcomes or contaminated by infra.

---

## Workstream 10 — Live corpus broadening

### Add tasks

```text
bugfix
test_generation
security_fix
migration
refactor
CI_failure
docs/lint
```

### Harnesses

```text
openai_harness gpt-4o-mini
claude_harness haiku
codex_cli if available
```

### Acceptance

At least 30–100 live/semi-live conclusive cells, with clear spend cap and redacted artifacts.

---

## Workstream 11 — Measurement mutation suite

### Mutations

```text
hide Claude key
enable provider retries
disable tool_choice required
force provider 500
force 429
force verification hang
force post-solve timeout
```

### Acceptance

ACP flags the mutation and prevents poisoned routing updates.

---

## Workstream 12 — Production health modes

### Extend

```bash
acp health --mode lab
acp health --mode staging
acp health --mode production
```

Production fails on:

```text
stale live Docker security
expected harness absent
provider timeout policy missing
inconclusive rate too high
coverage stale
artifact validation stale
capability matrix thin
OPE overlap poor
```

---

## Workstream 13 — Harness evolution proposal pipeline

### Build

```text
HarnessUpdateProposal
HarnessUpdateDiff
HarnessUpdateVerifier
HarnessNegativeTransferTest
HarnessUpdateReview
HarnessUpdateCanary
HarnessRollback
```

### Inputs

```text
failure traces
harness activation failures
adherence failures
review labels
post-merge outcomes
```

### Acceptance

Harness updates are PR-like, tested, reviewed, canaried, and reversible.

---

## Workstream 14 — Topology action learning

### Add actions

```text
skip_retrieval
skip_planner
skip_reviewer
skip_parallel
skip_strict_verification
run_light_verifier
run_strict_verifier
branch_parallel
terminate
abstain
```

### Tests

```text
learned skip reduces cost on docs/lint
security never skips strict verifier
ambiguous tasks skip implementation and route to spec
```

This directly incorporates the AgensFlow `skip:X` idea. 

---

## Workstream 15 — Relative trajectory judge

### Add

```text
RelativeTrajectoryJudge
CrossJudgeAudit
PerAxisReward
RewardSensitivityReport
```

### Axes

```text
task success
minimality
test adequacy
security
harness activation
harness adherence
recovery behavior
cost
```

### Acceptance

Preference learning can consume relative same-task trajectory rankings.

---

## Workstream 16 — Vendor harness live campaign

### Targets

```text
codex_cli
claude_agent_sdk
openhands
```

### Required evidence

```text
health
no-patch solve
trace
budget stop
timeout stop
secret non-leakage
Docker enforcement
verification
```

### Acceptance

At least one vendor-native harness has a committed live evidence pack.

---

## Workstream 17 — Docker live-security gate

### Build

```bash
acp eval docker-security-live
```

### Artifact

```text
evals/reports/docker_security_live.json
```

### Acceptance

Production mode refuses true harness execution without fresh passing Docker/Kubernetes security report.

---

## Workstream 18 — Local LoRA pilot

### Target

```text
Qwen2.5-Coder-1.5B-Instruct
```

### Dataset

```text
harness_activation
viability
evaluator_trust
repair_strategy
```

### Acceptance

Optional local smoke produces adapter, model card, memorization audit, baseline comparison.

---

## Workstream 19 — Large mixed live/semi-live corpus

### Goal

```text
500+ conclusive live/semi-live cells
multiple repos
multiple task types
multiple harnesses
multiple context strategies
cost-bounded
```

### Measure

```text
cost per conclusive success
HAR/HFR/PWL
infra failure rate
provider reliability
routing regret
Pareto profile performance
```

---

## Workstream 20 — Alpha 11 release bundle

Commit:

```text
ALPHA11_REPORT.md
ALPHA11_CHECKLIST.md
evals/reports/measurement_hygiene.json
evals/reports/provider_budget_policy.json
evals/reports/harness_availability_audit.json
evals/reports/tool_activation_metrics.json
evals/reports/harness_adherence_metrics.json
evals/reports/capability_matrix_v2.json
evals/reports/cost_aware_ope_v2.json
evals/reports/live_cells_ingest.json
evals/reports/policy_dossier_v2.json
evals/reports/live_corpus_broadening.json
evals/reports/measurement_mutation_suite.json
evals/reports/production_health.json
evals/reports/harness_update_pipeline.json
evals/reports/topology_skip_learning.json
evals/reports/relative_trajectory_judge.json
evals/reports/vendor_harness_live.json
evals/reports/docker_security_live.json
```

Gate:

```bash
uv run pytest -q --timeout=300
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha10-artifacts
make alpha11-artifacts
acp reports validate
acp health --mode lab
acp health --mode production
```

---

# Merge recommendation

Round 10 is a strong alpha checkpoint. I would merge it into an alpha/preproduction branch after:

```text
1. Refresh reports/coverage.txt.
2. Confirm acp reports validate covers all 24 artifacts.
3. Confirm acp health output is committed or attached.
4. Clearly label Docker/vendor/LoRA live gates as skipped, not passed.
```

For anything production-facing, the required next gates are:

```text
Docker live-security
vendor harness live campaign
measurement hygiene / infra classification
cost-aware routing consistency
real-cell persistence into capability matrix
```

The latest sprint’s live bakeoff is extremely valuable because it exposed measurement bugs. The next stage should focus less on adding new abstractions and more on making the live empirical loop **clean, trustworthy, cost-aware, and non-poisoning**.
