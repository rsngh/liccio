## Executive verdict

The branch is now a **serious alpha-to-preproduction routing lab**, not merely an agent-control-plane prototype. The current `feat/agent-control-plane` status reports **670 passing tests, 9 skipped, ruff/mypy clean across 192 source files, and Alembic upgrade OK**.  The branch status describes Alpha 9/10 as a multi-objective decision system plus scale-hardening layer: Pareto routing, drift demotion, preference learning, counterfactual regret, active-learning exploration, continuous-learning scheduling, unified health, a large empirical corpus, scale benchmarks, security-injection benchmarks, and model/data governance. 

I would now describe the project as:

> **A policy-governed empirical routing platform for coding-agent work, with learned governance, multi-objective routing, active safety gates, and a training-data pipeline from agent exhaust.**

It is still **not production-ready for arbitrary untrusted real-world repos**. The remaining blockers are no longer architecture gaps; they are validation, live-environment hardening, vendor-harness proof, real-data volume, and operational productization. Alpha 10 itself states that Docker live-security, vendor-harness live campaigns, and local LoRA training are environment-gated and skip cleanly when Docker/vendor keys/GPU are unavailable. 

One concrete housekeeping issue: the test report is current at Alpha 9/10, but `reports/coverage.txt` is still labeled Alpha 6, even though `CURRENT_STATUS.md` points to it.  Refreshing coverage should be part of the next cleanup commit.

---

# What has been implemented

## 1. Core control-plane loop

The original plan called for a system that can ingest tasks, compile context, route to agents, run safely, verify, evaluate, collect traces, learn, and improve. That is substantially implemented.

`CURRENT_STATUS.md` lists the durable core loop as:

```text
task → context → route → attempt → verify → evaluate → human → reward → learn
```

with durable resume, full provenance, adaptive routing, evaluation ladder, mediated command execution, context compiler, verification, observability, post-merge loop, API/CLI, and long evals. 

The status doc also states that every run persists task, snapshot, context pack, plan, decision, attempts, diffs, verification runs, evidence, evaluation, weak labels, rewards, and spans. 

## 2. Multi-harness empirical routing foundation

The branch still carries the Alpha 4 milestone: two true tool-loop harnesses, `openai_harness` and `claude_harness`, normalized `AgentTrace`, a multi-harness no-patch bakeoff, router learning from bakeoffs, and evaluator calibration. 

That addresses the early “do we have real harnesses?” gap. The system now has at least ACP-native true harnesses, although some vendor-native harness paths are still gated or not fully proven.

## 3. Viability assessment

Alpha 7 added the key primitive for “which requests are viable with which resources?” Every run now produces a `ViabilityAssessment` that can decide cheap-vs-harness, abstain on ambiguous/unverifiable tasks, and constrain routing. 

The `ViabilityAssessment` schema records task/risk, ambiguity, testability, evidence, viable agent classes, viable context strategies, required verification, model strength, cheap-model viability, true-harness requirement, human-review requirement, parallelism, abstention, confidence, and supporting features. 

This is one of the most important product primitives in the entire branch.

## 4. OPE promotion gate

The OPE promotion gate is implemented and correctly framed: offline policy evaluation alone is not enough to deploy a policy. `routing/promotion.py` checks statistical trust and operational safety, including effective sample size, propensity overlap, max importance weight, DR CI lower bound, SNIPS agreement, cost, human-review rate, high-risk degradation, and calibration.  

That is exactly the right architecture: a router policy should not be promoted just because a point estimate is high.

## 5. Capability matrix

The capability matrix aggregates empirical evidence by:

```text
task_type × risk_level × repo_type × agent_class × context_strategy × verification_policy
```

with metrics for success, cost, latency, human-review rate, post-merge failure, OPE reward, calibration confidence, sample size, and update time. 

It also refuses to recommend low-sample cells. This “no overclaim” behavior is explicitly documented. 

Alpha 10 reports that the large empirical corpus now contains **930 sufficiently sampled capability cells** and **1,740 preference pairs**, which is a major jump from the earlier small synthetic datasets. 

## 6. Training-data factory and learned governance

Alpha 8 and Alpha 7 together added the training-data factory and learned governance.

Alpha 7 states that ACP distills redacted, leakage-audited datasets from run exhaust and recommends fine-tuning only when justified.  Alpha 8 goes further: it adds learned viability, context-strategy learning, evaluator-trust modeling, repair-strategy classification, completed dataset builders for previously stubbed dataset kinds, model promotion/memorization audit, canary execution, and exploration planning. 

Alpha 8’s headline report says learned viability reached 1.0 accuracy with zero high-risk false negatives on the labeled set, context-strategy prediction reached top-1 accuracy 1.0 in the deterministic artifact, evaluator-trust thresholds cut low-risk human-review burden by 33%, repair strategy classification reached 0.95 accuracy, canary rollback works, and exploration is directed. 

The limitation is important: those learned models are based on synthetic or small distilled sets, not broad real production data. 

## 7. Multi-objective Pareto routing

Alpha 9 adds the right next layer: routing is no longer purely scalar. It reasons over multiple objectives.

`routing/pareto.py` computes the non-dominated frontier over:

```text
success ↑
cost ↓
latency ↓
risk ↓
```

and uses profile-specific weights to pick a frontier point. 

The Alpha 9 checklist says there is also a `ParetoRoutingPolicy` with six profiles:

```text
cost_saver
balanced
success_max
risk_min
latency_min
human_review_min
```

and that it exposes OPE targets per profile. 

This is a big product leap because the “best” agent is not singular; it depends on task risk, budget, latency, and operational tolerance.

## 8. Drift detection and auto-demotion

Alpha 9 adds drift detection: accuracy drop, PSI, and recent high-risk false-negative rate. The module demotes a promoted learned model back to advisory when drift is detected or when recent high-risk false negatives appear. 

The implementation has an `AutoDemoter` that flips `learned_promoted` back to false when the drift report recommends demotion. 

This is the correct safety posture for learned viability and evaluator models.

## 9. Preference learning

Alpha 9 adds preference learning from human labels. The module derives pairwise preferences between attempts for the same task and fits a Bradley-Terry/logistic-style preference model to produce a learned reward. 

The checklist says this is now part of Alpha 9’s delivered workstreams. 

This is valuable because human labels are often more reliable as pairwise preferences than as absolute scalar judgments.

## 10. Counterfactual regret

Alpha 9 adds per-decision counterfactual analysis. It answers: for this logged decision, what would each alternative action have been expected to yield, and what regret did the logged action incur? 

The module exposes both per-decision `what_if` and log-wide `total_regret`. 

This turns routing into an explainable learning system: not just “what policy is better?” but “which individual decisions left value on the table?”

## 11. Active learning, scheduler, and health

Alpha 9 includes active-learning exploration, a continuous-learning scheduler, and unified `acp health`. The checklist says the exploration executor turns capability-matrix gaps into budget/risk-bounded probes, and the scheduler runs the learning pipeline idempotently and fault-tolerantly. 

The status report says `acp health` now returns a unified control-plane snapshot with status/degraded state and artifact freshness. 

This is moving toward operational maintainability.

## 12. Scale and security hardening

Alpha 10 adds the scale/security layer:

```text
large empirical corpus
storage/performance benchmark v2
security/prompt-injection benchmark v2
model/data governance
```

The Alpha 10 report says the large corpus has 930 sufficiently sampled cells and 1,740 preference pairs, the scale benchmark shows sub-quadratic growth across six core operations, the security benchmark covers 10 attack classes with zero planted-secret leakage, and governance prevents private-repo data from entering the global training pool without allowlist. 

The Alpha 10 checklist confirms those workstreams and lists Docker live-security, vendor live campaigns, and local LoRA as environment-gated skips. 

---

# What has not been implemented or remains insufficiently proven

## 1. Production-grade live sandbox proof is still missing

Docker live-security remains environment-gated. Alpha 10 says Docker live-security requires Docker and skips cleanly here.  The current pytest report also says Docker workspace tests are skipped. 

This is the biggest production-readiness blocker. The code may support Docker; the committed default test evidence does not prove the live Docker path.

## 2. Vendor-native harness campaigns are still gated

The same Alpha 10 report says vendor-harness live campaign is environment-bound.  The test report says live Codex CLI/SDK tests are skipped. 

So ACP has ACP-native harnesses and vendor scaffolding, but production-grade evidence across Codex/Claude Agent SDK/OpenHands-style loops is still incomplete.

## 3. Local LoRA / actual fine-tuning remains gated

Alpha 8 says local LoRA fine-tuning remains a smoke path because no GPU is present; Alpha 10 says local LoRA is still environment-gated.  

So the training-data pipeline is mature, but actual repeated local model improvement is not yet proven.

## 4. Coverage report is stale

`reports/pytest.txt` is current for Round 10, but `reports/coverage.txt` is still labeled Alpha 6 at 87%.  

This is not a core product issue, but it matters for reviewer trust.

## 5. Synthetic/deterministic artifacts still dominate many claims

Alpha 9 and Alpha 10 artifacts are manifest-validated, but Alpha 9 explicitly says artifacts use synthetic/deterministic data so they are reproducible; richer inputs come from the Alpha 10 corpus and live campaigns. 

Synthetic artifacts are useful, but the platform now needs increasing amounts of live and semi-live data.

## 6. Governance exists, but enforcement boundaries need live adversarial proof

Model/data governance is reported as implemented: no private repo data enters global training without allowlist, repo-local training is permitted, and rollback plans are recorded. 

The next proof should not just validate policy objects; it should run adversarial data-boundary tests across repos, datasets, model exports, and training artifacts.

## 7. Human-review productization is still not the main focus

The system now has human labels, preference learning, and training examples. But it is not yet a product-grade review UX/workflow. The backend is advancing; the next hard step is making review efficient, calibrated, and useful to real engineers.

## 8. Pareto routing must be user-configurable and governed

Pareto profiles exist, but your sprint note correctly identifies “live `ParetoRoutingPolicy` selection via config” as a natural follow-on. The branch status says Pareto routing exists, but production deployment requires explicit profile selection, auditability, OPE promotion per profile, and per-repo defaults. 

---

# Constructive feedback

## 1. Stop adding standalone modules until the live decision path is tightened

The architecture is rich now. The next value is not another isolated evaluator. It is a **closed, governed, operational path**:

```text
request → viability → candidate generation → Pareto profile → OPE gate → execution → verification → human/reward → drift/preference/counterfactual → scheduler → next policy
```

Every new module should be visible in the run graph, policy dossier, health snapshot, and artifacts.

## 2. Make Pareto profiles first-class product settings

Add explicit profile selection:

```text
repo default profile
task-type default profile
risk-level override
budget override
human-review override
security override
```

The user should be able to say:

```text
For docs/lint: cost_saver
For bugfix: balanced
For auth/security: risk_min
For incident response: success_max with strict verifier
```

Then persist the chosen profile and rationale in every `RoutingDecision`.

## 3. Treat `acp health` as the operational entry point

The health snapshot should become the single “can we trust this control plane?” answer.

It should return:

```text
green / degraded / red
why
which artifacts are stale
which policies are promotable
which learned models are demoted
which capability cells are under-sampled
which live gates are skipped
which vendor harnesses are unproven
what to run next
```

## 4. Make artifact validation non-negotiable

You now have 24 manifest-validated artifacts according to `CURRENT_STATUS.md`.  Good. Add a policy that no Alpha report can be merged unless:

```text
all referenced artifacts exist
all schemas validate
all headline numbers match artifact values
all stale report files fail CI
```

## 5. Make Docker live-security a release blocker for real agents

Local tests may skip Docker, but “production-like real agent execution” should not.

Define modes:

```text
lab mode: Docker optional
trusted local dev: Docker optional
real harness mode: Docker live security report required
production mode: Docker/Kubernetes policy report required
```

## 6. Push vendor harnesses from scaffold to evidence

The next big product moat is not more ACP-native harnesses. It is making ACP a router across real tools:

```text
Codex CLI / SDK
Claude Agent SDK / Claude Code
OpenHands
Aider
Cline/Roo
```

Each needs the same normalized `AgentTrace`.

## 7. Convert preference learning into reviewer calibration

Pairwise preference learning is good, but it can encode reviewer bias. Add:

```text
reviewer agreement
reviewer reliability
domain expertise
preference drift
post-merge correlation
```

Only use preference reward where reviewers agree and outcomes support it.

## 8. Move from synthetic corpus to mixed corpus

The large corpus is a good scale artifact. Now build tiers:

```text
synthetic deterministic
fixture-generated
semi-live local harness
live model API
real repo replay
post-merge outcome replay
```

Reports should show which tier each result came from.

---

# Tests and stress tests to add

## A. Pareto routing in live workflow

Test:

```text
cost_saver selects cheaper frontier point
success_max selects higher-success harness
risk_min avoids high post-merge failure
latency_min avoids slow harness
human_review_min avoids high-review-burden arm
```

And assert:

```text
profile persisted
frontier persisted
dominated candidates persisted
chosen rationale persisted
run graph exposes profile/frontier
review bundle shows trade-off
```

## B. Pareto profile OPE gate

For each profile:

```text
cost_saver
balanced
success_max
risk_min
latency_min
human_review_min
```

run:

```text
OPE report
promotion gate
cost cap
risk slice
human-review slice
overlap diagnostics
```

Assert bad-overlap profiles cannot become default.

## C. Drift lifecycle end-to-end

Use a promoted learned viability model, then simulate:

```text
accuracy drop
PSI drift
one high-risk false negative
drift recovery
label delay
conflicting outcomes
```

Assert:

```text
drift report persisted
model demoted
audit event persisted
review item created
health degrades
scheduler records the job
policy falls back to rules
```

## D. Preference learning under reviewer disagreement

Simulate:

```text
multiple reviewers
tie labels
uncertain labels
conflicting preferences
reviewer bias
post-merge contradiction
```

Assert:

```text
low agreement blocks preference reward promotion
high agreement enables advisory reward
post-merge conflict deweights reviewer
preference model uncertainty visible
```

## E. Counterfactual regret trust tests

For each decision:

```text
supported alternative
low-sample alternative
zero-overlap alternative
high-risk task
conflicting reward model
```

Assert regret is:

```text
reported with support counts
hidden or marked untrusted when support is weak
excluded from health if insufficient overlap
```

## F. Active-learning exploration executor tests

Given capability matrix gaps and OPE poor-overlap cells, assert:

```text
exploration tasks generated
risk budget enforced
cost budget enforced
high-risk exploration requires human approval
exploration improves coverage in simulation
exploration improves OPE overlap
```

## G. Continuous-learning scheduler fault tests

Test:

```text
idempotency
partial failure
stale artifact
failed dataset build
failed OPE
failed drift job
resumption
duplicate prevention
parallel scheduler invocation
```

Assert the scheduler produces a partial report and clear retry plan.

## H. Control-plane health degradation tests

Health should become degraded/red when:

```text
artifact manifest stale
coverage stale
Docker live gate missing in production mode
vendor harness unproven
OPE overlap poor
policy promotion expired
drift demoted model
capability cells under-sampled
training dataset leakage audit fails
```

## I. Security-injection v3

Extend the 10 attack classes to include:

```text
training-data poisoning
reward-model poisoning
policy-promotion poisoning
artifact-manifest tampering
counterfactual-report tampering
review-label manipulation
repo boundary escape
secret canary extraction
dependency compromise
test harness spoofing
```

Assert every attack is blocked, escalated, or flagged.

## J. Data governance adversarial tests

Create:

```text
private repo A
private repo B
global dataset
repo-local dataset
allowlisted dataset
non-allowlisted dataset
```

Assert:

```text
private repo A does not leak into global
repo B cannot query repo A examples
fine-tuning export enforces policy
memorization canaries retained for audit but not training
rollback plan exists for model artifacts
```

## K. Large-corpus replay stress

Scale beyond the current large corpus:

```text
10k tasks
100k traces
1M context chunks
10M artifact references if feasible through synthetic refs
```

Measure:

```text
run graph latency
artifact validation latency
capability matrix build
OPE log build
counterfactual report
scheduler runtime
health snapshot runtime
```

## L. Vendor harness live campaign

Run live, environment-gated tests for:

```text
codex_cli
claude_agent_sdk
OpenHands
```

Each must prove:

```text
health
no-patch solve
diff capture
tool/command trace
timeout stop
budget stop
Docker requirement
secret non-leakage
verification result
```

## M. Local LoRA smoke

Run a real local LoRA smoke outside default CI:

```text
Qwen2.5-Coder-1.5B-Instruct
dataset: viability or evaluator
tiny sample
one epoch or short run
adapter save/load
baseline comparison
memorization audit
```

---

# Next-level plan for an LLM coding agent

Below is an ambitious Alpha 11 plan. It assumes the coding agent will keep working continuously, commit in coherent chunks, run long gates, and update `IMPLEMENTATION_LOG.md`.

## Alpha 11 mission

Turn ACP from a **manifest-validated alpha lab** into a **production-readiness candidate** for controlled internal use.

The key acceptance question:

> Can ACP safely and repeatedly route real coding-agent work under explicit objectives, prove policy decisions with offline evidence, enforce data/sandbox governance, detect drift, and tell operators what to do next?

---

## Workstream 1 — Fresh release hygiene

### Tasks

1. Refresh `reports/coverage.txt` for Round 10.
2. Add a test that fails if `coverage.txt` is older than `pytest.txt` for the current alpha.
3. Ensure `CURRENT_STATUS.md`, `ALPHA9_REPORT.md`, `ALPHA10_REPORT.md`, `reports/pytest.txt`, and `reports/coverage.txt` agree.
4. Confirm both branches point to the same commit.

### Acceptance

```bash
uv run pytest tests/integration/test_docs_consistency.py -q
acp reports validate
```

No stale Alpha 6 coverage reference remains.

---

## Workstream 2 — Pareto routing live configuration

### Build

```text
ParetoRoutingConfig
ParetoProfileRegistry
RepoRoutingObjectivePolicy
TaskTypeRoutingObjectivePolicy
```

### Config examples

```yaml
profiles:
  docs: cost_saver
  lint: cost_saver
  bugfix: balanced
  ci_fix: latency_min
  security_fix: risk_min
  incident: success_max
```

### Integration

```text
candidate generation
RoutingDecision
full_run_graph
review bundle
policy OPE
acp health
```

### Tests

```text
same task with cost_saver chooses cheap arm
same task with success_max chooses harness
security task defaults to risk_min
explicit override audited
invalid profile blocked
```

---

## Workstream 3 — Policy decision dossier

### Build

```text
PolicyDecisionDossier
```

Contains:

```text
ViabilityAssessment
CapabilityMatrix cells
Pareto frontier
OPE estimate
promotion gate
counterfactual regret
preference reward
drift status
data sufficiency
cost/risk tradeoff
chosen action
why not other actions
```

### CLI/API

```bash
acp policy dossier <run-id>
GET /runs/{run_id}/policy-dossier
```

### Acceptance

Every nontrivial run can explain:

```text
why this agent
why this context
why this verifier
why this cost
why this risk
what would likely have happened otherwise
```

---

## Workstream 4 — Control-plane health as release gate

### Extend `acp health`

Modes:

```text
lab
staging
production
```

Production mode should fail if:

```text
Docker live security missing/stale
vendor harness live proof missing/stale
artifact manifest stale
OPE overlap insufficient
drift-demoted model still promoted
capability matrix coverage below threshold
coverage/test reports stale
```

### Acceptance

```bash
acp health --mode production
```

returns nonzero unless production gates are satisfied.

---

## Workstream 5 — Docker live-security campaign

### Build

```text
evals/scripts/run_docker_live_security.py
```

Checks:

```text
no network
non-root
memory cap
PID cap
workspace-only mount
secret scrub
massive stdout
timeout kill
cleanup
diff capture
```

### Artifact

```text
evals/reports/docker_security_live.json
```

### Acceptance

Production mode cannot claim true-harness-safe execution without this artifact.

---

## Workstream 6 — Vendor harness live campaign

### Implement or harden

```text
codex_cli
claude_agent_sdk
openhands
```

### Live tests

For each available harness:

```text
health
no-patch bugfix
timeout stop
budget stop
diff capture
AgentTrace capture
Docker enforcement
secret non-leakage
verification result
```

### Artifact

```text
evals/reports/vendor_harness_live.json
```

### Acceptance

At least one vendor-native harness is proven beyond ACP-native OpenAI/Claude.

---

## Workstream 7 — Preference reward governance

### Build

```text
ReviewerReliabilityModel
PreferenceRewardGate
PreferenceRewardReport
```

### Inputs

```text
pairwise labels
reviewer agreement
post-merge outcomes
objective verification
task/risk slices
```

### Gate

Preference reward may influence routing only if:

```text
pairwise accuracy above threshold
reviewer agreement above threshold
post-merge correlation positive
high-risk slice non-degraded
```

### Acceptance

Preference reward is advisory by default and promoted only with sufficient evidence.

---

## Workstream 8 — Drift/demotion persistence

### Add entities

```text
DriftReportEntity
ModelDemotionEvent
ModelPromotionState
```

### Behavior

```text
drift detected
model demoted
audit event created
review item created if high-risk FN
health degrades
scheduler records job
```

### Acceptance

Auto-demotion is durable and inspectable, not just in-memory.

---

## Workstream 9 — Active learning as an executor

### Build

```text
ExplorationExecutor
ExplorationRun
ExplorationBudget
ExplorationResult
```

### Inputs

```text
capability gaps
OPE overlap gaps
high counterfactual regret
uncertain viability
drift uncertainty
```

### Behavior

```text
propose probes
respect budget
respect risk constraints
execute safe probes
update matrix
update OPE logs
```

### Acceptance

Simulated exploration increases capability coverage and OPE overlap, and live exploration is gated by risk/cost.

---

## Workstream 10 — Continuous-learning scheduler productionization

### Build

```text
ScheduledJob
JobRun
JobDependencyGraph
SchedulerLock
```

### Jobs

```text
artifact validation
dataset build
capability matrix refresh
OPE refresh
Pareto profile report
drift detection
preference update
exploration planning
health snapshot
```

### Tests

```text
idempotent
resumable
single-writer lock
partial failure
retry
stale report alert
```

---

## Workstream 11 — Data governance red-team

### Attack classes

```text
private repo data enters global training
repo A examples in repo B model
memorization canary included in training
allowlist bypass
model artifact without rollback plan
dataset export before leakage audit
```

### Acceptance

All attacks blocked or flagged.

---

## Workstream 12 — Larger mixed empirical corpus

Generate/collect:

```text
5,000 tasks
20 fixture repos
6 task types
3 risk levels
6 context strategies
4 adapters
3 repetitions
```

Track:

```text
sufficient capability cells
preference pairs
OPE overlap
Pareto frontier size
drift windows
counterfactual regret
```

### Acceptance

The capability matrix has enough coverage for meaningful recommendations in all common task/risk classes.

---

## Workstream 13 — Realistic repo fixtures

Add richer fixtures:

```text
Python package with CLI
FastAPI service
React/TypeScript app
monorepo with shared package
database migration app
security/auth app
flaky CI repo
legacy refactor repo
```

Each should have:

```text
real tests
lint/type checks
known bugs
security fixtures
migration fixtures
generated files
decoy files
```

---

## Workstream 14 — End-to-end no-patch live bakeoff

Run a controlled live bakeoff on a subset:

```text
OpenAI harness
Claude harness
Codex CLI if available
simple model adapter
```

Across:

```text
bugfix
test generation
security
migration
refactor
```

Metrics:

```text
solve rate
verification pass
cost
latency
human-review need
diff size
adversarial findings
post-merge simulation
```

---

## Workstream 15 — Local LoRA pilot

### Model

Use:

```text
Qwen2.5-Coder-1.5B-Instruct
```

### Dataset

Start with:

```text
viability
evaluator trust
repair strategy
trace summary
```

### Gates

```text
temporal holdout
repo holdout
memorization audit
baseline comparison
high-risk false-negative check
model card
rollback plan
```

### Acceptance

Do not require quality improvement in CI; require a full reproducible artifact and honest result.

---

## Workstream 16 — Human review product backend

### API

```text
GET /reviews/queue
GET /reviews/{id}/bundle
POST /reviews/{id}/label
POST /reviews/{id}/preference
POST /reviews/{id}/make-eval-case
POST /reviews/{id}/make-training-example
```

### Bundle

```text
task
viability
routing dossier
Pareto tradeoff
diff
evidence
AgentTrace
counterfactual regret
preference prompt
calibration warning
recommended action
```

### Acceptance

A reviewer can produce labels, preferences, eval cases, and training examples from one screen/API bundle.

---

## Workstream 17 — UI/API surface for operators

Even a minimal web/API view should expose:

```text
control-plane health
capability matrix
policy dossier
artifact manifest
scheduler jobs
exploration plan
review queue
model registry
```

This can be backend-first; UI can follow.

---

## Workstream 18 — Artifact and report warehouse

Store reports as DB entities, not only files:

```text
Report
ReportArtifact
ReportMetric
ReportLineage
```

Support:

```bash
acp reports list
acp reports show
acp reports diff
```

### Acceptance

Every Alpha report is queryable and comparable over time.

---

## Workstream 19 — Production-mode policy pack

Define:

```text
lab policy
staging policy
production policy
```

Production policy:

```text
Docker live gate required
vendor harness proof required
no local true harness
OPE promotion required
human review required for high risk
private data governance enforced
coverage/test artifacts fresh
```

---

## Workstream 20 — Alpha 11 release bundle

Commit:

```text
ALPHA11_REPORT.md
ALPHA11_CHECKLIST.md
evals/reports/policy_dossier.json
evals/reports/docker_security_live.json
evals/reports/vendor_harness_live.json
evals/reports/preference_reward_gate.json
evals/reports/drift_persistence.json
evals/reports/exploration_executor.json
evals/reports/scheduler_report.json
evals/reports/data_governance_redteam.json
evals/reports/mixed_empirical_corpus.json
evals/reports/local_lora_pilot.json
evals/reports/control_plane_health_production.json
```

Gate:

```bash
uv run pytest -q --timeout=300
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make alpha9-artifacts
make alpha10-artifacts
make alpha11-artifacts
acp reports validate
acp health --mode lab
acp health --mode production
```

---

# Merge recommendation

Round 10 is a clean checkpoint. I would merge only after one final small hygiene commit:

```text
1. Refresh reports/coverage.txt for Round 10.
2. Confirm CURRENT_STATUS.md references the refreshed coverage report.
3. Run acp reports validate and acp health.
4. Ensure ALPHA9/10 artifact paths validate in CI.
```

Then open/merge the PR if the target is an alpha branch. For production-facing use, keep it gated until Docker live security and vendor harness live campaigns pass.

The project has reached the point where further progress should be judged less by “number of modules added” and more by whether the system can **operate safely over time**: choose under explicit objectives, prove policy changes, detect drift, avoid data leakage, survive live adversarial runs, and tell operators exactly what evidence is missing before it acts.
