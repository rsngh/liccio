## Executive assessment

The branch is now well past “prototype.” Based on the latest `feat/agent-control-plane` files and the attached sprint report, I would describe it as:

> **Alpha 6: a self-improving multi-harness routing lab for coding-agent work.**

It now implements most of the control-plane architecture we originally sketched: durable provenance, multi-harness traces, no-patch bakeoffs, offline policy evaluation, a supervised meta-router, joint agent/context routing, context-strategy benchmarking, human-review data plumbing, live OpenAI harness evidence, persisted eval artifacts, budget hard-stops, and a growing safety/evaluation lab. The sprint report says Round 6 completed 10 workstreams and reached **451 passed / 7 skipped** with ruff and mypy clean; the committed report in the branch matches that. 

The important caveat is that this is still a **lab**, not yet a production router for arbitrary external coding agents. The system now has ACP-native OpenAI/Claude harnesses and vendor harness shims, but the Codex/Claude Agent SDK/OpenHands-style vendor loops are still capability-gated scaffolding or not fully battle-tested. The Alpha 6 report is honest about this: the vendor shims are registered and degrade gracefully, but the Codex/Claude vendor harness paths are not yet proven as full SDK loops.  

My merge recommendation: **open the PR after the branch is fast-forwarded to include the coverage refresh/finalize commit, then require a review gate focused on OPE validity, real-harness evidence, Docker enforcement, artifact truth, and dataset scale.**

---

# What has been implemented

## 1. Alpha 6 status and test gate

The branch now presents itself as Alpha 6 and reports:

```text
451 passing
7 skipped
ruff clean
mypy clean
87% coverage
```

That appears in `CURRENT_STATUS.md` and is supported by committed `reports/pytest.txt` and `reports/coverage.txt`.   

This resolves the earlier stale 151/305/371-test-count confusion. The docs now look aligned at the current branch state.

## 2. Core durable control-plane loop

The core loop is implemented as a durable workflow:

```text
task → context → route → attempt → verify → evaluate → human review → reward → learn
```

`CURRENT_STATUS.md` lists durable resume, full provenance, adaptive routing, evaluation ladder integration, mediated command execution, context compilation, verification, observability, post-merge loop, API/CLI, and long evals as real/tested pieces. 

This is the backbone of the original architecture.

## 3. Full run provenance

The branch claims every run persists task, snapshot, context pack, plan, routing decision, attempts, diffs, verification runs, evidence, evaluation, weak label, reward, and spans, reconstructable through `all_for_task`. 

This matters because the entire product’s learning loop depends on turning every agent run into reusable training/evaluation data.

## 4. Offline policy evaluation

Alpha 6 adds serious OPE machinery: IPS, SNIPS, clipped IPS, doubly robust estimation, bootstrap confidence intervals, effective sample size, overlap, and weight-tail diagnostics. The `routing/ope.py` source explicitly implements this goal: estimating the value of a target routing policy from logs collected under a behavior policy without rerunning agents. 

The Alpha 6 report says the OPE artifact ranks greedy and supervised meta-router policies above the logged/random baselines under doubly robust estimation. 

This is an important conceptual jump: the system can now ask, “Should we deploy this new routing policy?” before paying for live A/B traffic.

## 5. Supervised meta-router

The supervised router exists and is intentionally simple/calibratable. It learns a reward predictor over `(context_key, action_key)` token features and implements the routing-policy protocol. The code comments explicitly contrast this with a tabular bandit: the supervised policy can generalize across agents, strategies, and task types rather than memorizing exact arms. 

That is directionally right. A tabular bandit is a good starting point; a supervised meta-router is the next useful step.

## 6. Joint agent × context-strategy routing

Alpha 6 makes context strategy part of routing. The checklist says the runner recompiles context using the routed strategy and persists `ContextPack.strategy == RoutingDecision.action.context_strategy`. 

This is a major milestone. The router is no longer deciding only “which model/agent?” It is starting to decide “which agent with which context strategy?”

## 7. Context-strategy benchmark

The context-strategy benchmark sweeps retrieval strategies across multiple synthetic repo fixtures and reports recall@k, MRR, token cost, latency, secret leakage, per-repo winners, and overall rankings. The code includes clean, large, and adversarial fixtures and compares strategies such as hybrid, keyword-only, embedding-only, test-focused, and minimal.  

This directly addresses one of the big missing pieces from earlier rounds: context strategy is now measurable.

## 8. ACP-native true harnesses

The branch now has true ACP-native OpenAI and Claude harnesses, both live-verified according to `CURRENT_STATUS.md`. They are distinguished from the older one-shot JSON-edit simple model adapters. 

The attached Round 5 report also describes a live OpenAI-vs-Claude bakeoff in which both solved the same no-patch task, with tool-call, cost, token, and latency metrics recorded. 

## 9. Vendor harness category

Alpha 6 adds a vendor harness category and a `CapabilityRegistry`, with `claude_agent_sdk` and `codex_cli` shims registered and degrading gracefully. 

This is the right abstraction, but it should be treated as **scaffolding** until those shims are proven through full live SDK/CLI loops.

## 10. Live OpenAI harness artifact

There is a committed redacted live OpenAI experiment showing:

```text
adapter: openai_harness
is_harness: true
status: succeeded
solved: true
verified_raises_on_zero: true
tool_calls: 1
file_writes: calculator.py
diff_lines: 10
input_tokens: 565
output_tokens: 79
estimated_cost_usd: 0.000386
latency_s: 3.346
```



That is exactly the kind of artifact a reviewer needs.

## 11. Human-review studio backend

Alpha 6 adds a human-review studio backend: a priority-sorted queue, a secret-free review bundle, and label-to-eval-case conversion. 

The older `HumanReviewService` file I inspected is still a simple in-memory queue abstraction, so the new “studio” functionality likely lives in service/API/CLI layers rather than replacing the base service. The high-level feature appears implemented, but it deserves targeted review because the standalone `HumanReviewService` remains intentionally minimal. 

## 12. OTLP exporter / observability

The Alpha 6 report says `OTLPSpanExporter` exports ACP spans through OpenTelemetry, and the checklist says it is verified against an in-memory collector.  

That is a meaningful upgrade from local JSONL-only tracing.

## 13. Docker workspace and sandbox posture

Docker workspace v1 now mounts a host git worktree into a throwaway container with network/memory/CPU/PID limits, non-root execution, configurable networking, and host-side diff capture. 

The status doc remains honest that Kubernetes is stubbed and local execution is not an OS-level sandbox. 

---

# What has not been implemented, or is not yet proven enough

## 1. Vendor-native harnesses are not battle-tested

The Alpha 6 report says `codex_cli` is available in the environment, but the vendor shims are not yet battle-tested against a full vendor SDK loop. 

That is now the biggest remaining gap relative to the original thesis. You have ACP-native harnesses, but the product should route among real coding-agent harnesses:

```text
OpenAI Codex / Codex CLI / Codex SDK
Claude Agent SDK / Claude Code-style loop
OpenHands SDK
possibly Aider / Cline / Roo / Goose-style adapters
```

## 2. OPE headline is synthetic/separable

The OPE headline is valuable, but the Alpha 6 report is clear that the result uses a synthetic, separable log to make estimator behavior auditable. On real ACP logs, signal will be noisier and overlap diagnostics matter. 

So the OPE machinery exists, but the evidence is not yet enough to trust an actual router deployment.

## 3. OPE artifact availability needs checking

`ALPHA6_REPORT.md` and `ALPHA6_CHECKLIST.md` both reference `evals/reports/ope.json`.  

When I tried to fetch that exact path from the branch, it returned not found. That may be a branch sync/path issue, but before merging, make sure all checklist artifacts are actually committed at the referenced paths.

## 4. Context-strategy benchmark is synthetic/offline

The context benchmark is solid scaffolding, but it uses synthetic repo fixtures and hashing embeddings by default. The file itself says it runs fully offline using default hashing embeddings and no API key. 

That is good for reproducibility, but it is not enough to prove context strategy quality on real repos.

## 5. The supervised meta-router is intentionally simple

The Alpha 6 report says the supervised meta-router is a linear/ridge model with a mean fallback. 

That is a sensible first implementation, but the next phase needs stronger feature engineering, calibration, temporal validation, and drift handling.

## 6. Human-review studio needs product-level proof

The checklist says the studio backend exists, but the old `HumanReviewService` remains a simple in-memory queue. 

That may be fine if the richer functionality sits elsewhere, but reviewers should specifically test the full flow:

```text
review queue → review bundle → human label → eval case → calibration dataset → routing reward
```

## 7. Docker security still appears skipped in default CI

The test report says skipped tests include Docker workspace, live pgvector, and live codex CLI. 

This is fine for ordinary CI, but before running untrusted real agents, Docker security must be validated in a Docker-capable environment.

## 8. No true fine-tuning/training lab yet

There is no first-class training/fine-tuning pipeline yet for:

```text
viability classifier
context selector
evaluator model
repair model
small local LoRA
distillation from traces
dataset versioning / splits
memorization audit
model promotion
```

Given your recent question about fine-tuning, this is now an obvious next moat.

---

# Constructive feedback

## 1. Promote “viability assessment” to a first-class object

The system now routes based on task/context/action features, but it should explicitly answer:

```text
What type of request is this?
Is it automatable?
Which harness classes are viable?
Which context strategies are viable?
Which verification policies are required?
Is a cheap model viable?
Is human review mandatory?
What are the abstention conditions?
```

Create:

```text
ViabilityAssessment
CapabilityRequirement
AutomationEligibility
ContextViability
VerificationViability
ModelStrengthRequirement
```

This should happen before routing. The router should consume the viability assessment.

## 2. Separate “ACP harness” from “vendor-native harness”

Use four adapter classes everywhere:

```text
deterministic_baseline: fake, patch
simple_model_adapter: one-shot JSON edit
acp_harness: OpenAIHarnessAdapter, ClaudeHarnessAdapter
vendor_harness: Codex CLI/SDK, Claude Agent SDK, OpenHands
```

The branch already has this vocabulary partially through `CapabilityRegistry`; make it visible in reports, API, CLI, and routing policies.

## 3. Treat OPE as a deployment gate, not proof by itself

OPE should be required before policy promotion, but promotion should require:

```text
overlap >= threshold
ESS >= threshold
weight_tail <= threshold
DR CI clears baseline
SNIPS agrees directionally
temporal holdout agrees
live canary agrees
```

The current synthetic OPE is useful, but real logs need stricter gates.

## 4. Expand context strategy evaluation to real tasks

The context benchmark now ranks strategies on synthetic fixtures. Next, evaluate context strategies on:

```text
the no-patch dataset
live harness success
token cost
human-review rate
post-merge outcomes
```

Do not optimize only gold-file recall. A strategy that recalls gold files but doubles cost and reduces success is not necessarily better.

## 5. Add a fine-tuning / training-lab layer

The branch is now producing exactly the right exhaust:

```text
task
repo snapshot
context pack
routing decision
AgentTrace
diff
verification evidence
weak labels
human labels
reward
delayed outcomes
```

Turn that into datasets for:

```text
viability classification
context strategy selection
human-review prediction
evaluator calibration
repair strategy
patch repair
trace summarization
```

Start with small classifiers and local LoRA, not whole-agent generation.

## 6. Create “reviewable evidence packs”

Each alpha release should include a report bundle that proves the claims without relying on prose:

```text
test report
coverage report
OPE report
context strategy report
live harness report
Docker security report
human review conversion report
policy replay report
post-merge replay report
```

The branch is close; make artifact path checks part of CI.

---

# Tests to add beyond the existing suite

## A. Artifact existence and consistency gate

Add a test that fails if `ALPHA6_CHECKLIST.md` names an artifact that is not committed.

Required:

```text
evals/reports/ope.json
evals/reports/context_strategy_benchmark.json
reports/live/alpha6_openai_experiment.json
```

The first two paths should be verified because they are referenced in the checklist. 

## B. OPE robustness tests

Create logs with:

```text
good overlap
poor overlap
zero overlap
extreme propensities
incorrect reward model
non-stationary reward
confounded behavior policy
heavy-tailed rewards
```

Assertions:

```text
poor overlap warns or blocks promotion
zero overlap blocks promotion
ESS threshold enforced
clipped mass reported
DR/SNIPS disagreement blocks promotion
bootstrap CI width blocks promotion
```

## C. OPE on real ACP logs

Run OPE over actual persisted `RoutingDecision` + `RewardEvent` logs from:

```text
multi-harness bakeoff
context-strategy benchmark
live OpenAI/Claude tasks
delayed-outcome replay
```

Compare:

```text
logged policy
bandit
supervised meta-router
cost-aware supervised meta-router
risk-aware supervised meta-router
```

## D. Policy promotion gate

A policy should not be promotable unless:

```text
OPE passes overlap/ESS/CI thresholds
real-log holdout passes
cost cap satisfied
human-review rate acceptable
security-risk tasks not degraded
calibration threshold satisfied
```

Test promotion failure paths.

## E. Joint context × agent routing test

For a fixed task, ensure the selected context strategy actually changes:

```text
RoutingDecision.action.context_strategy
ContextPack.strategy
retrieval trace strategy
context items
token estimate
```

The checklist claims this invariant; make it a high-level integration test. 

## F. Context strategy benchmark on no-patch tasks

Run:

```text
task × harness × context_strategy × repetition
```

Metrics:

```text
success
verification pass
token cost
latency
gold-file recall
AgentTrace complexity
human-review requirement
```

Assert the strategy winner is based on downstream success, not recall alone.

## G. Vendor harness live smoke tests

For each vendor shim:

```text
codex_cli
claude_agent_sdk
openhands_sdk
```

Test:

```text
health unavailable cleanly
health available if binary/key present
tool/file/command trace capture
workspace containment
budget stop
timeout stop
Docker-required governance
```

The status report says `codex_cli` is available but not battle-tested, so this should become the next live gate. 

## H. Docker live security gate

Run in Docker-capable CI:

```text
non-root
no-network
memory limit
PID limit
workspace mount only
secret scrub
cleanup
command timeout
massive stdout bounded
parent read blocked
```

Default CI can skip, but merge-to-main should require a Docker-capable gate before any real-agent deployment.

## I. Human-review studio e2e

Test:

```text
create high-risk run
review appears in priority queue
bundle excludes secrets
bundle includes diff/evidence/weak labels/trace/judge disagreement
human label persists
make_eval_case writes JSONL
eval case can be loaded into calibration dataset
reward/event updated
```

## J. Training dataset builder tests

Add dataset builders for:

```text
viability
routing
context_strategy
evaluator
repair
trace_summary
```

Tests:

```text
temporal split
repo split
deduplication
secret redaction
label availability
no leakage across train/test
JSONL schema validation
```

## K. Fine-tuning smoke test

On local hardware, run a tiny LoRA smoke test with a small model:

```text
Qwen2.5-Coder-1.5B-Instruct
10–50 examples
1 epoch
tiny context
```

The test does not need quality, only:

```text
dataset export works
training script starts
adapter saved
eval script loads adapter
baseline comparison runs
```

## L. Calibration from human labels

Grow evaluator calibration beyond synthetic examples:

```text
human labels
post-merge outcomes
adversarial patches
review outcomes
live harness failures
```

Assertions:

```text
Brier score reported
ECE reported
threshold differs by risk level
false auto-approve rate below configured cap
```

## M. Multi-repo stress test

Use at least:

```text
Python library
Python CLI
TypeScript frontend
mixed monorepo
security-sensitive app
migration app
```

Run:

```text
100 tasks × 2 harnesses × 5 context strategies
```

Track success, cost, recall, human-review rate, and router preference.

## N. Long-run operational soak

Run:

```text
thousands of workflows
concurrency > 8
mixed task types
mixed adapters
mixed context strategies
Docker if available
```

Track:

```text
RSS
FDs
DB locks
artifact growth
workspace leaks
trace reconstruction latency
policy-state growth
OPE log size
eval report size
```

---

# Next-level plan for an LLM coding agent

Below is a much more ambitious Alpha 7 sprint. It is intended to keep an LLM coding agent busy for a long continuous implementation pass.

## Alpha 7 mission

Turn ACP from a self-improving lab into a **policy-governed multi-agent routing platform with explicit viability classification and a training-data/fine-tuning pipeline**.

The acceptance question:

> Can ACP look at a request, decide what is viable, choose agent + model + context + verifier, prove the policy offline, run safely, produce training data, and improve a local classifier/evaluator model from the exhaust?

---

## Workstream 1 — Viability assessment as a first-class primitive

### Add schemas

```text
ViabilityAssessment
CapabilityRequirement
AutomationEligibility
ContextViability
VerificationViability
ModelStrengthRequirement
AbstentionReason
```

### Fields

```text
task_id
repo_id
task_type
risk_level
ambiguity_score
testability_score
available_evidence
viable_agent_classes
viable_context_strategies
required_verification
cheap_model_viable
true_harness_required
human_review_required
parallelism_recommended
abstain
abstention_reasons
confidence
supporting_features
```

### Integration

```text
classification node produces ViabilityAssessment
routing consumes ViabilityAssessment
policy constraints enforce it
full_run_graph includes it
human review bundle includes it
```

### Tests

```text
docs task -> cheap/simple/local viable
security task -> true harness + strict verifier + human review
ambiguous architecture task -> planning/human review
no tests/no spec -> abstain or spec-generation first
```

---

## Workstream 2 — Capability matrix

### Add entity

```text
CapabilityMatrix
```

Rows:

```text
task_type × risk_level × repo_type × agent_class × context_strategy × verification_policy
```

Columns:

```text
success_rate
cost
latency
human_review_rate
post_merge_failure_rate
OPE_estimated_reward
calibration_confidence
sample_size
last_updated
```

### CLI

```bash
acp viability matrix --repo <repo-id>
acp viability explain --task <task-id>
```

### Tests

```text
matrix builds from EvalRuns
matrix updates after delayed outcomes
matrix flags insufficient data
matrix blocks low-sample overclaim
```

---

## Workstream 3 — Training dataset factory

### Add schemas

```text
TrainingExample
DatasetVersion
DatasetSplit
DatasetBuildConfig
DatasetCard
RedactionReport
LeakageAudit
```

### Dataset kinds

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

### CLI

```bash
acp dataset build --kind viability
acp dataset build --kind routing
acp dataset build --kind evaluator
acp dataset build --kind repair
acp dataset export <dataset-id> --format jsonl
acp dataset audit <dataset-id>
```

### Mandatory behavior

```text
temporal split
repo split
deduplication
secret redaction
generated-file filtering
label provenance
schema validation
dataset card
```

---

## Workstream 4 — Local fine-tuning smoke path

### Target

Start with:

```text
Qwen2.5-Coder-1.5B-Instruct
```

for:

```text
viability classifier
failure-mode classifier
review-needed classifier
trace summarizer
```

### Implement

```text
training/exporters/openai_jsonl.py
training/exporters/hf_sft_jsonl.py
training/lora_smoke.py
training/evaluate_adapter.py
```

### Acceptance

```text
tiny dataset exports
LoRA smoke run starts and saves adapter
eval script loads adapter
baseline vs fine-tuned comparison report exists
no secrets in exported data
```

Do not require this in normal CI; mark it as a local/optional training gate.

---

## Workstream 5 — OPE promotion gate

### Add

```text
PolicyPromotionGate
PromotionDecision
PolicyCanaryPlan
```

### Gate conditions

```text
ESS >= threshold
overlap >= threshold
max weight <= threshold
DR CI lower bound beats baseline
SNIPS direction agrees
cost cap satisfied
human-review rate not worse
high-risk tasks not degraded
calibration threshold satisfied
```

### CLI

```bash
acp policy evaluate-offline
acp policy promotion-check <policy-id>
acp policy canary-plan <policy-id>
```

### Tests

```text
zero-overlap policy blocked
high-variance policy blocked
cost-regressing policy blocked
high-risk regression blocked
good synthetic policy passes
```

---

## Workstream 6 — Real-log OPE report

### Build from

```text
RoutingDecision
RewardEvent
EvalRun
PolicyObservation
PostMergeOutcome
```

### Compare

```text
logged
bandit
supervised
cost-aware supervised
risk-aware supervised
context-aware supervised
```

### Output

```text
evals/reports/real_log_ope.json
```

### Acceptance

Report includes diagnostics and refuses to overclaim if overlap is poor.

---

## Workstream 7 — Context-strategy downstream benchmark

### Matrix

```text
task × harness × context_strategy × repetition
```

Strategies:

```text
minimal
bug_reproduction
test_focused
architecture
recent_changes
prior_failures
symbol_graph
full_file
```

Metrics:

```text
gold recall
success
verification pass
cost
latency
human review
post-merge replay
```

### Acceptance

Router can learn context strategy from downstream success, not just recall.

---

## Workstream 8 — Vendor harness hardening

### Implement at least one real vendor loop

Pick one:

```text
codex_cli
claude_agent_sdk
openhands_sdk
```

### Required

```text
healthcheck
execute
tool/file/command trace
diff capture
budget stop
timeout stop
Docker required
unavailable gracefully
```

### Tests

```text
unavailable cleanly
live smoke if configured
no secret leak
Docker enforcement
AgentTrace complete
```

---

## Workstream 9 — Human-review studio e2e

### API

```text
GET /reviews/queue
GET /reviews/{id}/bundle
POST /reviews/{id}/label
POST /reviews/{id}/make-eval-case
POST /reviews/{id}/make-training-example
```

### Bundle

```text
task
viability assessment
routing decision
context summary
diff summary
agent trace
verification evidence
weak labels
judge disagreement
calibration warning
cost
risk
recommended action
```

### Tests

Full human label → eval case → calibration example → reward update.

---

## Workstream 10 — Delayed outcome realism

### Add outcome types

```text
merged
not_merged
review_rounds
revert
issue_reopened
followup_bug
incident
latency_regression
security_regression
developer_satisfaction
```

### Tests

```text
positive day-0 + negative delayed outcome reverses policy preference
high review burden penalizes reward
security regression strongly penalized
```

---

## Workstream 11 — Safety and prompt-injection benchmark

### Dataset

```text
print env
read parent dir
disable tests
delete tests
modify policy
exfiltrate network
hide malicious code
write outside workspace
```

### Run across

```text
openai_harness
claude_harness
vendor harness if available
simple model
```

### Acceptance

No raw secrets in DB/artifacts/logs; malicious changes flagged or blocked.

---

## Workstream 12 — Docker live release gate

### Script

```bash
acp eval docker-security-live
```

### Output

```text
evals/reports/docker_security_live.json
```

### Checks

```text
non-root
no-network
memory cap
pid cap
workspace-only mount
cleanup
secret scrub
timeout
massive stdout
```

### Acceptance

Production-real-agent mode cannot be marked safe without this passing.

---

## Workstream 13 — Storage and scale benchmark

### Generate

```text
1,000 tasks
10,000 traces
100,000 context chunks
1,000,000 vector records if feasible
```

### Measure

```text
run graph reconstruction latency
OPE log build latency
context retrieval latency
artifact store growth
DB query latency
policy-state growth
```

### Acceptance

No obvious O(N²) path in core queries.

---

## Workstream 14 — Observability export hardening

### Add

```text
acp trace export --format jsonl|otlp
acp eval export --format json|parquet
```

### Optional integrations

```text
Braintrust
LangSmith
Phoenix
```

Even if stubs, they must have honest health states.

---

## Workstream 15 — Cost governance

### Add persisted

```text
BudgetEvent
BudgetLedgerSnapshot
BudgetPolicyVersion
```

### Enforce

```text
per-run cap
per-eval cap
per-agent cap
per-repo cap
daily cap
```

### Tests

Budget violations stop harness loop before unbounded cost.

---

## Workstream 16 — Generated-file and artifact hygiene

### Ensure

```text
__pycache__
*.pyc
.coverage
.pytest_cache
dist/
build/
node_modules/
```

are excluded from source diff metrics and trace quality metrics.

### Tests

Live artifacts and synthetic tasks should not count generated files as meaningful source changes.

---

## Workstream 17 — Multi-repo no-patch corpus expansion

Grow to:

```text
100+ tasks
6+ fixture repos
6 task types
3 risk levels
2+ true harnesses
5+ context strategies
```

### Acceptance

Router reports task-type and repo-type differences with confidence intervals.

---

## Workstream 18 — Fine-tuning candidate report

### Add

```bash
acp train candidate-report
```

Report:

```text
available examples by dataset kind
label quality
train/test split sizes
secret audit
baseline score
expected fine-tuning target
recommended base model
```

### Acceptance

The system recommends fine-tuning only when data quality/sample size is adequate.

---

## Workstream 19 — Alpha 7 release artifacts

Commit:

```text
ALPHA7_REPORT.md
ALPHA7_CHECKLIST.md
evals/reports/viability_matrix.json
evals/reports/real_log_ope.json
evals/reports/context_downstream_benchmark.json
evals/reports/vendor_harness_smoke.json
evals/reports/docker_security_live.json
evals/reports/training_candidate_report.json
```

### Gate

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make security-redteam
make bandit-monte-carlo
make retriever-stress
make alpha6-artifacts
make alpha7-artifacts
```

---

# Merge / branch recommendation

Because your sprint note says `feat/acp-round6` has a finalize commit and `feat/agent-control-plane` may lag by that one commit, I would **wait for the coverage refresh/finalize commit, then fast-forward `feat/agent-control-plane` once**. The current branch files I inspected already show the Alpha 6 coverage report and 451-test status, so if that is the latest remote state, open the PR now.

Before merge, require:

```text
1. Artifact path check: every checklist artifact exists.
2. OPE promotion gate includes overlap/ESS/CI thresholds.
3. Docker live security either passes or is explicitly marked release-blocking for production real-agent mode.
4. Vendor shims are labeled “registered but not battle-tested.”
5. Context-strategy benchmark is extended from recall-only to downstream harness success.
6. Full PR evidence bundle is attached.
```

The project is now at the point where the most valuable work is no longer “add more plumbing.” The next leap is **decision quality**: explicit viability classification, real-log OPE, context-strategy downstream learning, vendor harness hardening, and a training-data/fine-tuning pipeline from ACP exhaust.
