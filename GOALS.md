## Executive assessment

The current `feat/agent-control-plane` branch is now a **large, coherent alpha system** rather than a proof of concept. The Round 10 checkpoint reports **670 passing tests, 9 skipped, ruff/mypy clean across 192 source files, and Alembic upgrade head OK**. 

The branch now implements the majority of the original plan:

```text
agent/control-plane loop
repo-aware context compilation
multi-agent / multi-harness routing
evaluation ladder
weak supervision
human review
reward and delayed-outcome machinery
OPE / policy promotion gates
capability matrix
training-data factory
learned governance
Pareto routing
drift detection
preference learning
counterfactual regret
continuous-learning scheduler
large empirical corpus
security/prompt-injection benchmark
model/data governance
```

The best short description is:

> **ACP is now a policy-governed empirical routing platform for coding-agent work.**

It is still **not production-ready for arbitrary untrusted real-world repos**. The remaining issues are now mostly around **live validation, operational hardening, real vendor harness proof, dataset realism, Docker/Kubernetes safety, and actual model fine-tuning** rather than basic architecture.

The project direction is also highly aligned with the two recent research papers you uploaded. AgensFlow argues that multi-agent systems should learn auditable coordination policies over task signatures, skills, model bindings, topology, skipping, and reward audit rather than rely on fixed pipelines.  The harness-evolution paper argues that harness-updating and harness-benefit are distinct capabilities, and that agents need explicit training/evaluation around harness activation and adherence.  ACP has implemented much of the first idea; the second idea is now one of the clearest next moats.

---

# What has been implemented

## 1. Core durable agent-control-plane loop

The core loop exists and is tested:

```text
task → context → route → attempt → verify → evaluate → human review → reward → learn
```

`CURRENT_STATUS.md` lists this as a durable workflow runner and says the system persists full provenance: task, snapshot, context pack, plan, decision, attempts, diffs, verification runs, evidence, evaluation, weak labels, reward, and spans. 

This satisfies the original architecture’s foundation.

## 2. Multi-harness empirical router

The branch has two real ACP-native tool-loop harnesses, `openai_harness` and `claude_harness`, normalized `AgentTrace`, no-patch bakeoffs, and routing learning from bakeoff outcomes. 

This is important because the original thesis was not “build one more coding agent.” It was to build an independent control plane that can compare and govern different agents/harnesses.

## 3. Viability assessment

ACP now has first-class request viability assessment. Every run produces a `ViabilityAssessment` that decides whether the task is viable, whether cheap models are sufficient, whether a true harness is required, whether human review is mandatory, which context strategies are viable, and whether ACP should abstain. 

The schema includes the right decision fields:

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



This directly implements the “which request types are viable with which models/context?” direction.

## 4. Offline policy evaluation and promotion gate

ACP now has OPE and a policy-promotion gate. The gate is designed to block policies with high point estimates but weak support. It checks statistical trust and operational safety: effective sample size, propensity overlap, max importance weight, DR confidence interval, SNIPS agreement, cost cap, human-review rate, high-risk degradation, and calibration.  

This is one of the strongest pieces in the branch. A router should not be promoted merely because it looks good offline.

## 5. Capability matrix

The capability matrix aggregates evidence by:

```text
task_type × risk_level × repo_type × agent_class × context_strategy × verification_policy
```

It tracks success, cost, latency, human-review rate, post-merge failure, OPE reward, calibration confidence, sample size, and update time. 

It also refuses to overclaim: low-sample cells are flagged, and `best_for` will not recommend them. 

Alpha 10 reports **930 sufficiently sampled capability cells** and **1,740 preference pairs**, which is a meaningful scale-up for a lab setting. 

## 6. Learned governance from ACP exhaust

Alpha 8 added learned governance from run exhaust: learned viability, context-strategy prediction, evaluator trust, repair strategy classification, model-governance gates, memorization audit, canary simulation, and directed exploration. 

The report says learned viability hit 1.0 accuracy on a labeled set with zero high-risk false negatives, evaluator trust reduced low-risk human-review burden by 33%, and repair classification reached 0.95 accuracy over a nine-class taxonomy. 

The caveat is explicit: these learned models are trained/evaluated on synthetic or small distilled sets, and real promotion needs more logged traffic. 

## 7. Classical ML exists, but not PyTorch training

The repo has real lightweight ML:

```text
scikit-learn-style supervised predictors
learned viability predictor
context-strategy predictor
preference scorer
supervised meta-router
bandits / OPE / drift / Pareto / counterfactuals
```

But it does not use PyTorch in the default path. The dependency file includes `scikit-learn` in optional `data` and `learning` extras, but no default PyTorch dependency. 

The local LoRA module explicitly imports cleanly without `torch`, `peft`, or `transformers`; it returns a skipped record if those are unavailable, and the full non-smoke LoRA path is explicitly not implemented.  

So the honest characterization is:

> **ACP has real classical/statistical ML. It does not yet have real deep-learning fine-tuning.**

## 8. Multi-objective Pareto routing

Alpha 9 added Pareto routing. The implementation computes a non-dominated frontier over:

```text
success ↑
cost ↓
latency ↓
risk ↓
```

and uses weight profiles to pick a frontier point. 

The checklist says Alpha 9 has a `ParetoRoutingPolicy` with six profiles:

```text
cost_saver
balanced
success_max
risk_min
latency_min
human_review_min
```

and that the same candidates can produce different rational choices depending on the profile. 

This is a major product feature: “best model” is not singular. It depends on user objective.

## 9. Drift detection and auto-demotion

Alpha 9 added drift detection for learned models. It monitors accuracy drop, PSI, and recent high-risk false negatives, then demotes a learned model back to advisory if drift appears. 

The implementation includes an `AutoDemoter` that flips `learned_promoted` back to `False`. 

This is the right safety loop for learned viability/evaluator models.

## 10. Preference learning

Alpha 9 added preference learning from human labels. The module converts human labels into pairwise preferences and fits a Bradley-Terry-style scorer over attempt features. 

This matches the product need: human feedback is often more useful as “attempt A was better than attempt B” than as a standalone scalar score.

## 11. Counterfactual regret

ACP now includes per-decision counterfactual analysis. It asks: for a logged decision, what would each alternative have been expected to yield, and what regret did the logged choice incur? 

The implementation exposes per-decision `what_if` and log-wide `total_regret`. 

This is valuable for explainability: not just “policy B is better,” but “this specific run left this much value on the table.”

## 12. Active learning, scheduler, and health

Alpha 9 includes active-learning exploration, a continuous-learning scheduler, and unified `acp health`. The checklist says active learning turns capability-matrix gaps into budget/risk-bounded probes, and the scheduler runs ordered jobs idempotently and fault-tolerantly. 

`CURRENT_STATUS.md` says `acp health` returns a unified snapshot with status/degraded state and artifact freshness. 

This is the beginning of real operator support.

## 13. Scale and security hardening

Alpha 10 adds a large empirical corpus, a storage/performance benchmark, expanded security/prompt-injection benchmarks, and model/data governance. The Alpha 10 report says:

```text
930 sufficiently sampled capability cells
1,740 preference pairs
sub-quadratic storage/perf behavior
10 attack classes all escalated or flagged
zero planted-secret leakage
private-repo data blocked from global training without allowlist
```



The Alpha 10 checklist confirms the delivered workstreams and explicitly says Docker live-security, vendor-harness live campaign, and local LoRA remain environment-gated. 

---

# What has not been implemented or remains insufficiently proven

## 1. Production-grade Docker/live sandbox proof is still missing

Docker workspace tests are skipped in the committed test report. 

The code and gates exist, but for production-like execution of untrusted real agents, the branch still needs a Docker-capable live report proving:

```text
no-network enforcement
non-root execution
memory cap
PID cap
timeout enforcement
workspace-only mount
secret scrubbing
cleanup
diff capture
```

## 2. Vendor-native harnesses are still not live-proven

The Alpha 10 report says the vendor-harness campaign is environment-bound.  The test report says live Codex CLI/SDK and service backends are skipped. 

ACP-native OpenAI/Claude harnesses are useful, but the original idea was to route across the fast-growing landscape of actual coding agents. The next moat is live evidence for:

```text
Codex CLI / SDK
Claude Agent SDK / Claude Code
OpenHands
Aider
Cline/Roo
Goose
```

## 3. Fine-tuning is still not operational

The branch has a training-data factory and fine-tuning governance, but local LoRA is still environment-gated and not run in CI. 

The LoRA module confirms that full training is not wired and the path mostly reports readiness/skips. 

## 4. Coverage is stale

`reports/pytest.txt` is Round 10 current, but `reports/coverage.txt` is still labeled Alpha 6.  

This is easy to fix, but important for trust.

## 5. Synthetic artifacts still dominate

Alpha 9 explicitly notes that artifacts use synthetic/deterministic data so they are reproducible and that richer inputs require Alpha 10 large corpus and live campaigns. 

Alpha 10 expands scale, but live and production-replay evidence is still limited.

## 6. Skill/harness evolution is not yet fully represented

The research you uploaded emphasizes harness evolution: updating prompts, skills, memories, and tools from execution evidence while keeping the base model fixed. 

ACP has training-data and governance pieces, but it does not yet appear to have a full PR-like harness-evolution pipeline:

```text
HarnessUpdateProposal
HarnessDiff
HarnessUpdateEval
SkillRegressionSuite
NegativeTransferReport
HumanReview
Canary
Rollback
```

That is now a high-leverage next step.

## 7. Harness activation and adherence metrics are missing or underdeveloped

The harness-benefit paper shows that weak models often fail either to activate relevant harness artifacts or to follow them over the trajectory, and it uses metrics like skill-load rate, harness-following rate, and pass-when-loaded. 

ACP has normalized traces, but it should explicitly measure:

```text
harness_candidate_retrieved
harness_loaded
harness_load_valid
harness_followed
harness_adherence_by_phase
pass_when_loaded
adherence_decay
harness_abandonment_turn
```

This is important because routing should consider not just “can model X solve?” but “can model X benefit from the harness?”

## 8. Topology skipping is not first-class enough

AgensFlow treats `skip:X` as a routing action and shows topology compression can be learned.  ACP has context strategy and Pareto routing, but it should make workflow topology actions first-class:

```text
skip_retrieval
skip_planner
skip_reviewer
skip_parallel
skip_strict_verification
run_light_verifier
branch_parallel
terminate
abstain
```

---

# Constructive feedback

## 1. Cut a clean Round 10 release checkpoint

Round 10 is a strong checkpoint. Before going further, make it reviewable:

```text
refresh coverage
validate artifacts
ensure CURRENT_STATUS matches pytest/coverage
add ALPHA10 evidence bundle index
run acp health
```

The repo is now large enough that every major claim needs a corresponding artifact.

## 2. Reframe the product around “decision dossiers”

Each significant routing decision should produce a dossier:

```text
ViabilityAssessment
CapabilityMatrix evidence
Pareto frontier
OPE estimate
Promotion gate
Counterfactual regret
Preference reward
Drift status
Data sufficiency
Chosen action
Rejected alternatives
Cost/risk trade-off
```

That would make ACP not just a router but an explainable engineering decision system.

## 3. Treat Pareto profile as a user/business policy

The system should let teams configure objective profiles:

```text
docs/lint → cost_saver
bugfix → balanced
CI outage → latency_min
security/auth → risk_min
incident → success_max
```

Each profile should have hard safety constraints and OPE promotion history.

## 4. Make Docker live-security a production gate

The current implementation correctly skips Docker when unavailable. But “true harness production mode” should refuse to run without a recent passing Docker/Kubernetes security report.

## 5. Prioritize vendor-native harness proof

The next real product unlock is showing ACP can route across existing external coding agents, not only ACP-native wrappers.

Start with:

```text
Codex CLI
Claude Agent SDK / Claude Code
OpenHands
```

and require normalized `AgentTrace` for each.

## 6. Implement harness-benefit metrics

Add the metrics from the harness-benefit paper:

```text
Skill Load Rate / Harness Activation Rate
Harness Following Rate
Pass When Loaded
Phase-level adherence
Adherence drift
Activation failure reason
Adherence failure reason
```

This should become part of the capability matrix.

## 7. Build a governed harness-evolution pipeline

Harness updates should be treated like code changes:

```text
propose
diff
test
redact
security scan
negative-transfer test
human review
canary
promote
rollback
```

Do not let an evolver mutate production harness state directly.

## 8. Add topology learning

Inspired by AgensFlow, topology should be learnable, not static. Add `skip:X` and “run/skip” decisions to the action space, with reward/cost/quality tracking. 

## 9. Replace “ML claims” with model inventory

Given the repo uses mostly classical ML and statistical methods, add:

```bash
acp ml inventory
```

It should report:

```text
model name
kind
backend
trained?
uses_torch?
uses_sklearn?
input features
target
promotion status
drift status
```

This will prevent confusion about whether ACP is using PyTorch/deep learning.

---

# Additional tests and stress tests

## A. Release truth tests

Add tests that assert:

```text
reports/pytest.txt matches CURRENT_STATUS
reports/coverage.txt is current
all ALPHA10_CHECKLIST artifacts exist
all artifact metrics match ALPHA10_REPORT
acp reports validate covers 24/24 artifacts
acp health returns expected status
```

## B. Docker live-security test

In Docker-capable CI:

```text
no network
non-root
memory cap
PID cap
timeout kill
workspace-only mount
secret scrub
massive stdout bounded
cleanup
diff capture
```

This should produce:

```text
evals/reports/docker_security_live.json
```

## C. Vendor harness live campaign

For each vendor harness:

```text
codex_cli
claude_agent_sdk
openhands
```

test:

```text
health available/unavailable
no-patch bugfix
timeout stop
budget stop
tool trace
file trace
command trace
diff capture
verification pass/fail
secret non-leakage
Docker enforcement
```

## D. Pareto live-run tests

For the same task/candidates, assert:

```text
cost_saver chooses cheap adapter
success_max chooses strongest harness
risk_min chooses low post-merge-risk arm
latency_min chooses fast arm
human_review_min chooses low-review-burden arm
```

Persist:

```text
profile
frontier
dominated candidates
chosen score
trade-off summary
```

## E. OPE + Pareto profile tests

For each Pareto profile:

```text
OPE estimate
ESS
overlap
DR CI
SNIPS
cost cap
high-risk slice
human-review slice
```

Assert profiles with poor overlap or unacceptable cost/risk are blocked.

## F. Drift lifecycle e2e

Simulate:

```text
baseline window
recent degraded window
high-risk false negative
recovery window
```

Assert:

```text
drift report persisted
model demoted
audit event created
review item created
health degraded
scheduler records job
fallback policy activated
```

## G. Preference learning robustness

Test:

```text
multiple reviewers
reviewer disagreement
ties/uncertain labels
objective pass but human reject
human prefer but post-merge revert
reviewer bias
```

Assert preference reward remains advisory unless agreement and post-merge correlation pass thresholds.

## H. Counterfactual uncertainty tests

For counterfactual regret:

```text
supported alternative
low-sample alternative
zero-overlap alternative
high-risk alternative
conflicting reward model
```

Assert unsupported regret is marked untrusted, not shown as fact.

## I. Harness activation/adherence benchmark

For each harness/model:

```text
harness retrieved
harness loaded
valid load format
first-step adherence
midpoint adherence
final adherence
pass when loaded
```

Track:

```text
HAR
HFR
PWL
adherence_decay
activation_failure_reason
adherence_failure_reason
```

## J. Harness-evolution grid

Separate evolver and task agent:

```text
evolver ∈ cheap, mid, strong
task agent ∈ cheap, mid, strong
```

Measure:

```text
harness-update quality
task solve gain
harness activation
harness adherence
cost
negative transfer
```

This tests the “spend capability on the task-solving agent, not necessarily the evolver” hypothesis from the harness-evolution paper. 

## K. Topology skip ablation

Compare:

```text
fixed full pipeline
no-skip
learned skip
always skip retrieval
always skip verifier
always strict verifier
```

Measure:

```text
success
cost
latency
human review
post-merge failure
token usage
```

This directly imports the AgensFlow `skip:X` insight. 

## L. Harness update governance red-team

Attack classes:

```text
write secret into skill
disable verifier in skill
add unsafe network guidance
teach agent to skip tests
poison reward model
poison training dataset
overfit to one task
negative transfer to unrelated tasks
```

Assert proposal is blocked, flagged, or requires human review.

## M. Long-run soak

Run:

```text
5,000–20,000 workflows
mixed task types
mixed profiles
mixed adapters
some Docker
some human-review
some post-merge outcomes
scheduler enabled
```

Track:

```text
RSS
FDs
DB locks
artifact growth
run graph latency
capability matrix build time
OPE build time
scheduler duration
health snapshot latency
```

---

# Next-level plan for an LLM coding agent

Below is an ambitious Alpha 11/12 plan meant for a long continuous implementation pass.

## Alpha 11 mission

Turn ACP from an alpha routing lab into a **controlled preproduction platform** with live sandbox proof, vendor harness evidence, policy dossiers, and harness-benefit metrics.

---

## Workstream 1 — Release hygiene and artifact truth

### Tasks

1. Refresh `reports/coverage.txt`.
2. Add `test_report_freshness.py`.
3. Ensure `CURRENT_STATUS.md`, `reports/pytest.txt`, and `reports/coverage.txt` match.
4. Add artifact schemas for all Alpha 9/10 reports.
5. Add `acp reports diff`.

### Acceptance

```bash
acp reports validate
uv run pytest tests/integration/test_docs_consistency.py -q
```

No stale Alpha 6 coverage file remains.

---

## Workstream 2 — Policy decision dossier

### Add

```text
PolicyDecisionDossier
```

Includes:

```text
ViabilityAssessment
CapabilityMatrix evidence
Pareto frontier
OPE estimate
promotion gate
counterfactual regret
preference reward
drift status
human-review threshold
chosen action
rejected alternatives
```

### CLI/API

```bash
acp policy dossier <run-id>
GET /runs/{run_id}/policy-dossier
```

### Acceptance

Every real run has a reviewable reason for why the chosen agent/context/verifier was selected.

---

## Workstream 3 — Pareto profile configuration

### Add

```text
ParetoProfileRegistry
RepoRoutingObjectivePolicy
TaskTypeRoutingObjectivePolicy
```

### Config

```yaml
profiles:
  docs: cost_saver
  lint: cost_saver
  bugfix: balanced
  ci_fix: latency_min
  security_fix: risk_min
  incident: success_max
```

### Acceptance

Same candidate set yields different choices under different profiles, and every override is audited.

---

## Workstream 4 — Docker live-security gate

### Build

```bash
acp eval docker-security-live
```

### Artifact

```text
evals/reports/docker_security_live.json
```

### Checks

```text
no network
non-root
memory cap
PID cap
workspace-only mount
secret scrub
timeout
massive stdout
cleanup
diff capture
```

### Acceptance

`acp health --mode production` fails without a fresh passing Docker live report.

---

## Workstream 5 — Vendor harness live campaign

### Targets

```text
codex_cli
claude_agent_sdk
openhands
```

### Contract

```text
health
no-patch solve
budget stop
timeout stop
tool/file/command trace
diff capture
verification
secret non-leakage
Docker enforcement
```

### Acceptance

At least one vendor-native harness has a committed live evidence artifact.

---

## Workstream 6 — Harness activation/adherence metrics

### Add schemas

```text
HarnessActivationReport
HarnessAdherenceReport
HarnessBenefitMetrics
```

### Metrics

```text
HAR = harness activation rate
HFR = harness following rate
PWL = pass when loaded
phase_adherence
adherence_decay
activation_failure_reason
adherence_failure_reason
```

### Acceptance

Capability matrix includes harness-benefit metrics by model/harness/task type.

---

## Workstream 7 — Harness evolution pipeline

### Add

```text
HarnessUpdateProposal
HarnessUpdateDiff
HarnessUpdateReview
HarnessUpdateEval
HarnessUpdateCanary
HarnessUpdateRollback
```

### Flow

```text
execution evidence → evolver proposal → diff → redaction/security → regression tests → negative-transfer tests → human review → canary → promote/rollback
```

### Acceptance

No persistent harness update can merge without eval, audit, and rollback metadata.

---

## Workstream 8 — Topology action learning

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

### Update

```text
RoutingAction
CandidateGenerator
OPE logs
CapabilityMatrix
ParetoRouter
```

### Acceptance

ACP can learn workflow shape, not just agent/model/context.

---

## Workstream 9 — Relative trajectory judge

### Add

```text
RelativeTrajectoryJudge
CrossJudgeAudit
PerAxisReward
RewardSensitivityReport
```

### Axes

```text
goal achievement
test adequacy
minimality
security
harness activation
harness adherence
recovery behavior
cost
```

### Acceptance

Preference learning can consume relative trajectory comparisons.

---

## Workstream 10 — Preference reward governance

### Add

```text
ReviewerReliabilityModel
PreferenceRewardGate
PreferenceRewardReport
```

### Gate

Preference reward may affect routing only if:

```text
reviewer agreement high
post-merge correlation positive
high-risk non-degradation
pairwise accuracy acceptable
```

---

## Workstream 11 — Drift persistence

### Add entities

```text
DriftReportEntity
ModelDemotionEvent
ModelPromotionState
```

### Acceptance

Auto-demotion persists audit events, health state, and fallback policy activation.

---

## Workstream 12 — Exploration executor productionization

### Inputs

```text
low-sample capability cells
poor OPE overlap
high regret
uncertain viability
drift windows
```

### Output

```text
budgeted exploration plan
risk constraints
expected sample gains
```

### Acceptance

Simulated exploration improves capability coverage and OPE overlap.

---

## Workstream 13 — Continuous-learning scheduler hardening

### Jobs

```text
artifact validation
dataset build
OPE refresh
capability refresh
Pareto reports
drift detection
preference update
exploration planning
health snapshot
```

### Tests

```text
idempotent
resumable
locked
partial failure
stale artifact alert
duplicate prevention
```

---

## Workstream 14 — Data governance red-team

### Attacks

```text
private repo → global dataset
repo A → repo B model
memorization canary in training
allowlist bypass
model artifact without rollback plan
dataset export before leakage audit
```

### Acceptance

All attacks blocked or flagged.

---

## Workstream 15 — Local LoRA pilot

### Model

```text
Qwen2.5-Coder-1.5B-Instruct
```

### Dataset

```text
viability
evaluator trust
repair strategy
trace summary
```

### Outputs

```text
adapter
model card
memorization audit
baseline comparison
repo holdout
temporal holdout
```

### Acceptance

Optional/live only, but real training must run when deps/hardware exist.

---

## Workstream 16 — Larger mixed corpus

Generate:

```text
5,000+ tasks
20 fixture repos
6 task types
3 risk levels
6 context strategies
4 adapters
3 repetitions
```

Goal:

```text
>2,000 sufficient capability cells
>10,000 preference pairs
usable OPE overlap for common task classes
```

---

## Workstream 17 — Operator health modes

Add:

```text
acp health --mode lab
acp health --mode staging
acp health --mode production
```

Production should fail on:

```text
stale artifacts
missing Docker live gate
unproven vendor harness
poor OPE overlap
demoted learned model still active
private-data governance failure
```

---

## Workstream 18 — UI/API backend for review and policy operations

Add:

```text
GET /health/control-plane
GET /capability-matrix
GET /policy-dossier/{run_id}
GET /reviews/queue
POST /reviews/{id}/preference
POST /harness-updates/{id}/review
GET /reports
GET /scheduler/jobs
```

This can remain backend-first.

---

## Workstream 19 — Production policy pack

Define:

```text
lab_policy.yaml
staging_policy.yaml
production_policy.yaml
```

Production policy:

```text
Docker live gate required
vendor harness proof required
OPE promotion required
human review for high risk
local harness disallowed
private data governance enforced
fresh test/coverage reports required
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
evals/reports/harness_benefit_metrics.json
evals/reports/harness_update_pipeline.json
evals/reports/topology_skip_ablation.json
evals/reports/relative_trajectory_judge.json
evals/reports/preference_reward_gate.json
evals/reports/drift_persistence.json
evals/reports/exploration_executor.json
evals/reports/scheduler_hardening.json
evals/reports/data_governance_redteam.json
evals/reports/local_lora_pilot.json
evals/reports/mixed_corpus_v2.json
evals/reports/production_health.json
```

### Gate

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

Round 10 is strong enough to merge into an alpha branch after one final hygiene pass:

```text
1. Refresh reports/coverage.txt.
2. Confirm CURRENT_STATUS.md references the refreshed coverage.
3. Run acp reports validate.
4. Run acp health.
5. Clearly mark Docker/vendor/LoRA live gates as skipped, not passed.
```

For anything production-facing, keep it gated until Docker live security and vendor harness live campaigns pass.

The next leap should not be more standalone algorithms. It should be **closed-loop operational trust**: policy dossiers, live sandbox proof, vendor harness proof, harness activation/adherence metrics, governed harness evolution, topology learning, and production-mode health gates.
