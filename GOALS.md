## Executive verdict

This branch is a **legitimate, working v0 of the agent-control-plane concept**, and it has moved beyond the earlier scaffold stage. It now has a real Python package, CLI/API, schemas, SQLAlchemy persistence, local worktree execution, deterministic fake/patch agents, context compilation, verification, objective evaluation, weak supervision hooks, active-learning hooks, a simulated bandit policy, persisted run state/spans, run inspection endpoints, and long-test targets.

But it is **not yet the ambitious product described in the plan**. It is best described as:

> **A local, no-key, end-to-end prototype of the control-plane loop, with several production primitives started but not yet hardened.**

The most important remaining gaps are: real coding-agent SDK integrations, Docker/Kubernetes sandboxing, real vector/embedding stores, durable crash-resume under actual failure injection, serious eval/bakeoff infrastructure, complete routing-policy integration, production observability, and large-scale stress testing.

One notable update since the earlier state: the code now has persistent `RunState` and `Span` tables, expanded run-inspection API endpoints, a live `SimulatedBanditPolicy` inside `AppService`, stronger command-runner containment/scrubbing, and workflow-runner changes for weak supervision / active learning / policy injection. The `FINAL_REPORT.md` is therefore partly stale: it still lists cross-process resume as future work, but newer code has begun implementing run-state persistence and rehydration. 

---

# 1. What has been implemented

## Project foundation

Implemented well.

The branch defines a Python-first `acp` package with `uv`, Typer CLI, FastAPI, Pydantic, SQLAlchemy/Alembic, GitPython, structlog, optional context/learning/observability groups, and test/lint/type config. The repo advertises the core loop as `task → context → route → attempt → verify → evaluate → human label → reward → learn`. 

The Makefile includes the expected targets for unit/integration/e2e tests, coverage, soak, bakeoff, bandit Monte Carlo, retriever stress, chaos, and security red-team runs. 

**Assessment:** strong base.

---

## Core data model and persistence

Substantially implemented.

The DB model now includes the core entities: repositories, repo snapshots, tasks, context packs/items, routing decisions, agent attempts, tool calls, command runs, diff bundles, verification plans/runs, evidence, evaluation results, human-review items/labels, weak labels, reward events, policy versions, post-merge outcomes, artifacts, audit logs, plus newly added `run_states` and `spans`. 

This is a major step toward the original “every agent run becomes a reusable training example” premise.

**What is still uncertain/incomplete:** the tables exist, but I would not assume the entire provenance graph is fully persisted and reloadable under all crash scenarios until the new persistent-resume path is tested with actual process death at every node. The current final report claims 151 tests, but coverage is only about 83%, below the original 85% target. 

**Assessment:** good schema foundation; needs rigorous full-graph replay tests.

---

## API surface

Improved since the prior inspection.

The FastAPI app supports repo/task creation, run start, run state, run trace, run diff, run evidence, run evaluation, run cancel, review list/get/label/resolve, and policy list/train/promote/rollback.  

That is meaningfully closer to the plan than the earlier API state.

**Still missing:** repo indexing endpoint, eval replay/bakeoff endpoints, trace-by-trace endpoint, artifact-download endpoint, context-pack inspection endpoint, adapter health endpoint, live policy metrics endpoint, post-merge outcome ingestion endpoint, and full run replay endpoint.

**Assessment:** API is now more than a demo surface, but still not a complete product control plane.

---

## Command execution and workspace safety

Improved.

`CommandRunner` now uses robust `Path.is_relative_to` containment instead of string-prefix checks, supports secret scrubbing before launching child processes, still captures stdout/stderr artifacts, timeouts, process-group termination, redaction, and metadata.  

This is a strong improvement.

**Still incomplete:** network policy remains advisory in local execution; the code comment explicitly says hard no-network enforcement belongs to container backends.  The Docker workspace manager is still a stub and raises `NotImplementedError` when Docker is available. 

**Assessment:** local safety layer is stronger, but still not safe enough for untrusted real agents without container isolation.

---

## Workspace management

Implemented locally.

The system has local git-worktree isolation and diff capture. This is sufficient for deterministic patch/fake agent tests and local development.

**Still incomplete:** no real Docker/Kubernetes sandbox, no resource limits, no hard network isolation, no non-root execution, no volume-level secret prevention, no post-run container artifact capture.

**Assessment:** good local workspace primitive; production sandbox remains a top priority.

---

## Agent adapters

Implemented at v0 level.

The final report says the system runs end-to-end without paid keys using fake/patch adapters, and that OpenAI `SimpleLLMReviewAdapter` was live-tested against the bugfix fixture.  

**Still incomplete:** the final report explicitly lists Claude, Codex, and OpenHands as optional/stubbed/graceful fallback paths, not fully realized harness integrations. 

**Assessment:** good local deterministic adapters; not yet a real multi-coding-agent router.

---

## Context compiler

Implemented as a useful local version.

The system has indexing, retrieval, token budgeting, and context packs. It reportedly stress-tested a 400-file synthetic repo with a 5,000-token budget and deterministic context hashes. 

**Still incomplete:** pgvector, Qdrant, sentence-transformers, and production-grade embeddings are still listed as stubs/fallbacks.  The context test scale is also far too small for the target product.

**Assessment:** context compiler is a good prototype; the retrieval moat is still ahead.

---

## Evaluation ladder

Partially implemented, improving.

The runner now appears to import active learning, fake judges, weak supervision, and includes a `score_signals` node in `NODE_ORDER`, based on the current runner fetch.  The data model also has persisted `WeakLabel`. 

**Still incomplete:** I would treat the evaluation ladder as “wired enough to test,” not “done.” The next layer is to prove that weak labels, judge results, active-learning priorities, human labels, and post-merge outcomes actually affect routing rewards and policy updates in a measurable way.

**Assessment:** promising; needs calibration, adversarial tests, and live-loop validation.

---

## Routing and learning

Improved but not yet product-grade.

`AppService` now initializes a persistent in-process `SimulatedBanditPolicy`, passes it into `WorkflowRunner`, and policy train/promote/rollback API endpoints exist.  

**Still incomplete:** this is still a simulated/in-process bandit, not a durable production routing policy. The final report still lists MABWiser/VW as fallback/stubbed, and doubly robust off-policy evaluation is future work.  

**Assessment:** the live workflow is starting to learn, but the real routing/evaluation moat has not been validated yet.

---

## Observability

Improved.

The data model now has `spans`, and the current runner fetch shows `SpanRecord` and a tracer being used in the workflow.  

**Still incomplete:** production-grade OpenTelemetry export, LangSmith/Braintrust/Phoenix integrations, span completeness checks, and trace inspection UX are still not done; the final report lists those exporters as fallback/stubbed. 

**Assessment:** good local trace foundation; not yet observability productization.

---

## Long tests and stress tests

Targets exist, but many are too light.

The Makefile includes the right target names.  The repo claims bandit simulation, retriever stress, soak, and chaos results. 

But the current chaos test does not actually kill the worker mid-node; it runs the workflow to completion, then resumes the completed state.  That is useful for idempotent-finalization testing, but it is not a real crash-resume test.

**Assessment:** test scaffolding exists; production confidence still needs strenuous stress testing.

---

# 2. What has not been implemented or is still too thin

The biggest remaining gaps are:

1. **Real container sandboxing.** Docker/Kubernetes are stubs; local command execution cannot hard-block network/syscalls. 

2. **Real coding-agent harness adapters.** Fake/patch/OpenAI-lightweight exist, but Claude Agent SDK, Codex SDK, and OpenHands SDK are not production wrappers. 

3. **Real vector DB and embedding stack.** pgvector/Qdrant/sentence-transformers are not implemented as live retrieval backends. 

4. **Real crash-resume testing.** Run-state persistence has started, but the stress tests do not yet prove recovery after process death at arbitrary workflow nodes. 

5. **Production policy learning.** The current bandit is in-process/simulated. It needs persisted arms, replay, off-policy evaluation, confidence intervals, champion/challenger traffic splitting, and drift detection.

6. **Full provenance completeness.** The DB schema is broad, but the system needs a hard invariant: every completed run can be fully reconstructed from DB + artifact store without process memory.

7. **Serious eval datasets.** The tests are mostly small fixtures. The system needs task datasets with gold files, expected diffs, expected failures, and adversarial agent behaviors.

8. **Full API/CLI product surface.** Run inspection exists, but context pack inspection, artifact download, adapter health, eval runs, bakeoff reports, and post-merge outcome ingestion are still missing.

9. **Production observability.** Local spans are useful, but OTel/exporter integrations and trace completeness tests are not yet enough.

10. **Honest status docs.** `FINAL_REPORT.md` says “production-grade,” but the same file lists major production-critical components as stubs/fallbacks.  

---

# 3. Constructive feedback

## Reposition this as a strong v0, not production-grade

The branch is impressive, but “production-grade” is premature. I would update the docs to say:

> “A local, no-key, end-to-end v0 of the agentic software-engineering control plane, with durable provenance, sandboxing, real agent harnesses, and production learning in progress.”

That is more credible and still strong.

## Make provenance reconstruction the central invariant

The product’s moat is not the fake agent, the patch agent, or the heuristic router. It is the historical experience graph.

Add a test that fails unless this is true:

```text
Given only run_id, database, and artifact store,
the system can reconstruct:
task, repo snapshot, context pack, retrieval trace, routing decision,
candidate actions, agent attempts, workspaces, diffs, command runs,
verification plan/runs/evidence, weak labels, judge results,
human review, reward event, spans, audit events, and post-merge outcomes.
```

## Make sandboxing the next hard gate before real agents

Do not run real Claude/Codex/OpenHands agents on arbitrary repos through the local worktree runner. The command runner is better now, but local execution still cannot enforce hard no-network or syscall boundaries. The Docker backend should become mandatory for untrusted real-agent execution.

## Treat the current bandit as a policy prototype

The live in-process `SimulatedBanditPolicy` is useful, but production routing needs persisted policy state, replayable decisions, off-policy evaluation, and controlled exploration. Every routing decision should persist:

```text
feature vector hash
candidate actions
candidate scores
chosen action
action probability
policy version
exploration reason
constraints applied
reward event
delayed reward updates
```

## Push the context compiler toward measurable retrieval quality

The context compiler needs a benchmark with gold files/symbols, not just a “budget not exceeded” test. For each task, measure:

```text
gold file recall@5/10/20
symbol recall
test-file recall
context token cost
compile latency
secret leakage
duplicate context ratio
```

## Upgrade verification to detect agent cheating

Passing tests is not enough. Add fraud detectors for:

```text
deleted tests
weakened assertions
pytest.skip / xfail additions
snapshot-only updates
hardcoded outputs
broad exception swallowing
dead code patches
security-sensitive drift
coverage drops
mutation survivors
```

## Make bakeoff and soak outputs machine-readable

The long evals should produce JSON/Parquet reports with:

```text
run_id
task_id
repo
agent
model
context strategy
verification strategy
cost
tokens
latency
success
reward
failure class
human review required
review burden
context recall
artifact size
workspace cleanup status
```

These reports become router-training data.

---

# 4. Tests to add beyond the existing suite

## A. Provenance and persistence tests

**Full graph reconstruction test**

Run one full workflow, destroy `AppService`, create a new `AppService` with the same DB/artifact dir, then assert:

```text
get_run(run_id) works
run_trace(run_id) works
run_diff(run_id) works
run_evidence(run_id) works
run_evaluation(run_id) works
all artifacts resolve
all IDs in WorkflowState point to persisted rows
```

**All-for-task completeness test**

After a successful run, query `EntityStore.all_for_task(task_id)` and assert it includes at least:

```text
Task
RepoSnapshot
ContextPack
RoutingDecision
AgentAttempt
DiffBundle
VerificationPlan
VerificationRun
Evidence
EvaluationResult
WeakLabel
RewardEvent
SpanRecord
```

**Artifact integrity test**

For every artifact ref:

```text
file exists
checksum matches
path is inside artifact root
content is redacted
content type/suffix is sane
```

---

## B. Real crash-resume tests

The existing “chaos” test is not enough because it completes the run before resume.  Add a parameterized test over every workflow node:

```text
for node in NODE_ORDER:
    run until just after node persists
    simulate hard process death
    create new AppService
    reload WorkflowState
    resume
    assert exactly one finalization
    assert exactly one reward event unless delayed rewards exist
    assert no duplicate attempts/evidence/spans
```

Also add:

```text
crash while WAITING_FOR_HUMAN
restart
list open reviews
submit label
resume
finalize
```

And:

```text
resume high-risk WAITING_FOR_HUMAN run without label
assert it remains blocked
```

---

## C. Sandbox/security tests

**Prefix escape**

```text
allowed_root = /tmp/ws
cwd = /tmp/ws_evil
must fail
```

The new `Path.is_relative_to` change should pass this. 

**Symlink escape**

Inside workspace:

```text
link_to_outside -> /tmp/outside
```

Try to read/write through the symlink. The system should block or at least flag.

**Secret scrubbing**

Inject fake secrets through:

```text
os.environ
explicit env
task body
repo file
command stdout
command stderr
trace attributes
artifact content
LLM response
```

Search DB + artifacts + logs for raw secret strings.

**Docker no-network**

Once Docker backend lands:

```text
run curl against external URL
run curl against local test server
run DNS lookup
assert all fail when network disabled
```

**Resource exhaustion**

Inside Docker:

```text
fork bomb attempt
infinite file write
infinite stdout
memory hog
CPU spin
```

Assert limits work and artifacts remain bounded.

---

## D. Evaluator anti-gaming tests

Add malicious patch fixtures:

1. Deletes failing tests.
2. Adds `pytest.mark.skip`.
3. Weakens assertions.
4. Changes expected outputs instead of code.
5. Hardcodes exact test values.
6. Adds broad `except Exception: pass`.
7. Touches unrelated billing/auth files.
8. Updates snapshots only.
9. Removes type hints to avoid type-check failures.
10. Changes verification config to avoid running tests.

Expected behavior:

```text
tests may pass
evaluation should be suspicious
human review required
reward penalized
weak labels persisted
```

---

## E. Retrieval quality tests

Create `evals/datasets/context_gold.yaml`:

```yaml
- task: "Fix divide-by-zero behavior"
  repo: python_buggy_app
  gold_files:
    - src/calculator.py
    - tests/test_calculator.py
  gold_symbols:
    - divide
```

Then test:

```text
recall@5
recall@10
MRR
token budget
latency
duplicate chunks
secret leakage
```

Scale from:

```text
400 files
5,000 files
25,000 files
100,000 chunks
```

---

## F. Routing and policy tests

**Live policy update test**

Run 100 tasks with the live `SimulatedBanditPolicy`:

```text
assert arms update
assert candidate_actions > 1
assert action_probability persisted
assert rewards alter future choices
```

**Budget-constrained routing**

Set max cost to tiny value:

```text
assert expensive candidates filtered
assert constraints_applied records clamping
```

**Non-stationary drift**

Simulate:

```text
first 500 tasks: agent A best
next 500 tasks: agent B best
```

Assert:

```text
router adapts
drift alert fires
policy report shows degradation interval
```

---

## G. Real adapter live tests

Mark them `@pytest.mark.live`.

For each real adapter:

```text
healthcheck
tiny bugfix
token capture
diff capture
command/tool-call capture
budget stop
timeout stop
workspace containment
secret non-leakage
```

Adapters:

```text
OpenAI SimpleLLM
Claude Agent SDK
Codex SDK
OpenHands SDK
```

---

## H. Serious soak tests

Upgrade `make soak-6h` to capture:

```text
RSS memory
open file descriptors
workspace count
git worktree count
artifact count
artifact bytes
DB size
p50/p95/p99 latency
status distribution
failure classes
reward distribution
policy arm distribution
```

Fail if:

```text
memory grows > 25%
workspace leaks > 0
artifact growth unbounded
DB rows missing expected graph
error rate exceeds threshold
```

---

# 5. Ambitious two-day plan for an LLM coding agent

Below is a detailed implementation plan for a coding agent to run continuously for a couple of strenuous days. It is intentionally aggressive.

---

## Mission

Take the current v0 from “local prototype” to “credible alpha control plane.”

Primary objectives:

```text
1. Prove durable provenance and crash resume.
2. Implement Docker sandboxing for real-agent safety.
3. Wire evaluation/weak supervision/policy learning into the live loop.
4. Add retrieval quality benchmarks.
5. Add serious stress, security, and bakeoff reports.
6. Expand CLI/API inspection surfaces.
7. Leave the repo with stronger docs, CI, and a truthful status report.
```

Do not weaken existing tests. Do not remove security tests. Do not make live API tests required by default.

---

## Day 1, Block 1 — Baseline and status correction

### Tasks

1. Run:

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv run mypy src
make coverage
```

2. Save results to `IMPLEMENTATION_LOG.md`.

3. Update `FINAL_REPORT.md` or create `CURRENT_STATUS.md` with four sections:

```text
Implemented
Partial
Stubbed
Known risks
```

4. Make the status explicitly say:

```text
This is a local v0 / alpha, not production-grade.
```

5. Add/verify GitHub Actions:

```yaml
ruff
mypy
unit
integration
e2e
coverage
```

### Acceptance

```text
CI config exists.
Status docs match actual code.
No “production-grade” overclaim remains unless the missing pieces are implemented.
```

---

## Day 1, Block 2 — Full provenance reconstruction

### Tasks

1. Ensure `RunState` is mapped in `EntityStore` if not already.
2. Ensure `SpanRecord` is mapped in `EntityStore`.
3. Persist every run artifact:

```text
WorkflowState
Task
RepoSnapshot
ContextPack
VerificationPlan
RoutingDecision
AgentAttempt(s)
DiffBundle(s)
VerificationRun(s)
Evidence
EvaluationResult
WeakLabel
HumanReviewItem
HumanLabel
RewardEvent
SpanRecord(s)
AuditEvent(s)
```

4. Add `AppService.full_run_graph(run_id)` returning a structured object:

```json
{
  "state": {},
  "task": {},
  "snapshot": {},
  "context_pack": {},
  "routing_decision": {},
  "attempts": [],
  "diffs": [],
  "verification_runs": [],
  "evidence": [],
  "evaluation": {},
  "weak_labels": [],
  "review_items": [],
  "human_labels": [],
  "reward_events": [],
  "spans": [],
  "audit_events": []
}
```

5. Add API:

```text
GET /runs/{run_id}/graph
```

6. Add CLI:

```bash
acp run graph <run-id>
```

### Tests

```text
test_full_run_graph_contains_expected_entities
test_run_graph_survives_service_restart
test_every_id_in_workflow_state_resolves_to_row
test_artifact_refs_resolve_from_graph
```

### Acceptance

A run can be reconstructed from DB + artifact store without relying on `_runs` or `_runners`.

---

## Day 1, Block 3 — Real crash-resume harness

### Tasks

1. Add a debug/test hook to `WorkflowRunner`:

```python
stop_after_node: str | None = None
fail_after_node: str | None = None
```

2. For each node in `NODE_ORDER`, test:

```text
run until node persists
simulate crash by discarding runner/service
instantiate new AppService
load run state
resume
assert final state correct
```

3. Add special tests for human review:

```text
crash while WAITING_FOR_HUMAN
restart
list review
label review
resume
finalize
```

4. Add duplicate prevention:

```text
reward event count stable
attempt count stable
evidence count stable
finalize node appears once
```

### Tests

```bash
uv run pytest tests/integration/test_crash_resume.py -q
```

### Acceptance

Crash-resume works after every node and while blocked for human review.

---

## Day 1, Block 4 — Command-runner and local sandbox hardening

### Tasks

1. Ensure all verification commands run with `allowed_root` set to the specific workspace path, not the broad workspace parent.
2. Remove any unnecessary `allow_cwd_outside_root=True`.
3. Add `CommandRunner.run` local variable for `max_output_chars` rather than mutating instance state.
4. Persist every `CommandRunRecord` generated by verification.
5. Add symlink escape detection:

```text
cwd.resolve() must stay inside allowed_root.resolve()
output artifact path must stay inside artifact root
writes through symlinks should be detected where possible
```

6. Add audit event for any command that requests network or secrets.

### Tests

```text
test_command_prefix_escape_blocked
test_command_symlink_escape_blocked
test_command_max_output_override_does_not_mutate_runner
test_verification_command_records_persisted
test_no_command_env_secret_in_child_by_default
```

### Acceptance

Local command execution is materially safer and fully recorded.

---

## Day 1, Block 5 — Docker workspace v1

### Tasks

Implement `DockerWorkspaceManager`.

Minimum behavior:

```text
create temporary workspace directory
copy repo snapshot into workspace
start container from python:3.11-slim or configured image
mount workspace at /workspace
run as non-root if possible
network disabled by default
memory limit
CPU limit
pids limit
timeout
cleanup container
capture diff from mounted workspace
```

Add policy:

```python
WorkspacePolicy(backend="docker", allow_network=False, memory_mb=1024, cpus=1)
```

Add config:

```text
ACP_ENABLE_DOCKER
ACP_DOCKER_IMAGE
ACP_DOCKER_MEMORY_MB
ACP_DOCKER_CPUS
```

Add `WorkspaceManagerFactory`.

### Tests

Mark Docker tests skipped if Docker unavailable:

```text
test_docker_workspace_create_and_cleanup
test_docker_workspace_no_network
test_docker_workspace_nonroot_or_documented
test_docker_workspace_resource_limit
test_docker_workspace_diff_capture
```

### Acceptance

The system can run the bugfix demo inside Docker with no network.

---

## Day 1, Block 6 — Evaluation ladder integration

### Tasks

1. Create `EvaluationPipeline`:

```python
class EvaluationPipeline:
    def evaluate(task, attempt, diff, evidence, verdict, classification) -> EvaluationBundle:
        objective = ObjectiveEvaluator(...)
        weak_label = WeakSupervisor(...)
        judge_results = [...]
        al_score = ActiveLearningSelector(...)
        final = merge(...)
        return bundle
```

2. Wire it into `WorkflowRunner`.

3. Persist:

```text
WeakLabel
judge results if schema exists, else as evidence metadata
ActiveLearningScore if schema exists
human-review reason includes active-learning reason
```

4. Add fraud feature extraction:

```text
deleted_tests
weakened_tests
skip_added
xfail_added
coverage_drop
snapshot_only
unrelated_files
sensitive_files
```

### Tests

```text
test_bugfix_without_test_gets_weak_suspicious_label
test_large_diff_gets_active_learning_high_priority
test_security_diff_requires_human
test_parallel_disagreement_requires_review
test_weak_label_persisted_in_run_graph
```

### Acceptance

The live workflow uses objective + weak + AL signals, not just objective eval.

---

## Day 2, Block 1 — Routing policy becomes first-class

### Tasks

1. Add `CandidateGenerator`:

```text
candidate per available agent
candidate per context strategy
candidate per verification policy
candidate per budget tier
```

2. Ensure every decision has multiple candidates when multiple agents are available.
3. Persist feature vector hash and candidate scores.
4. Implement durable policy snapshot:

```text
PolicyVersion.params contains arms/stats
PolicyVersion.metrics contains success/cost/reward summaries
```

5. On reward:

```python
policy.observe_reward(policy_decision, reward)
```

6. Add `train_policy` to snapshot current bandit state.
7. Add off-policy report:

```text
IPS
SNIPS
mean reward by action
coverage of propensities
```

### Tests

```text
test_live_policy_decision_has_multiple_candidates
test_live_policy_arms_update_after_reward
test_policy_snapshot_persists_arms
test_policy_promote_and_rollback_affect_selection
test_ope_rejects_missing_propensity
```

### Acceptance

Routing is actually adaptive in the main workflow.

---

## Day 2, Block 2 — Context retrieval benchmark

### Tasks

1. Add `evals/datasets/context_gold.yaml`.
2. Create 20–50 synthetic tasks across fixture repos:

```text
bugfix
test generation
docs
security
migration
frontend
multi-file refactor
```

3. Implement `evals/scripts/run_context_benchmark.py`.

Metrics:

```text
recall@5
recall@10
MRR
token count
compile latency
duplicate chunk ratio
secret leakage count
```

4. Add 5k-file and 25k-file synthetic repo generators.
5. Add report output:

```text
evals/reports/context_benchmark.json
evals/reports/context_benchmark.md
```

### Tests

```text
test_context_benchmark_fixture_recall_threshold
test_context_benchmark_no_secret_leakage
test_context_benchmark_report_schema
```

### Acceptance

Context compiler quality is measurable, not anecdotal.

---

## Day 2, Block 3 — Real vector-store protocol

### Tasks

1. Add:

```python
class VectorStore(Protocol):
    def upsert(self, chunks): ...
    def query(self, vector, filters, top_k): ...
    def delete_snapshot(self, snapshot_id): ...
```

2. Implement:

```text
InMemoryVectorStore
PgVectorStore stub-or-real depending dependency
QdrantStore stub-or-real depending dependency
```

3. Add embedding providers:

```text
HashingEmbedder
OpenAIEmbedder optional
SentenceTransformerEmbedder optional
```

4. Add embedding cache keyed by:

```text
model
content_hash
dimensions
```

5. Wire `ContextCompiler` to optionally use vector store.

### Tests

```text
test_inmemory_vector_store_roundtrip
test_embedding_cache_reuses_content_hash
test_pgvector_unavailable_graceful
test_qdrant_unavailable_graceful
test_context_compiler_can_use_vector_store
```

### Acceptance

The architecture is ready for production retrieval backends even if live services are optional.

---

## Day 2, Block 4 — Serious bakeoff harness

### Tasks

Replace the current lightweight bakeoff with a matrix runner.

Inputs:

```yaml
repos:
  - python_buggy_app
tasks:
  - fixture_bugfix_tasks.yaml
agents:
  - patch
  - fake
  - simple_llm_if_available
context_strategies:
  - minimal
  - bug_reproduction
  - hybrid_keyword_embedding
verification_policies:
  - standard
  - strict
seeds: [1,2,3,4,5]
```

Outputs:

```text
evals/reports/bakeoff.json
evals/reports/bakeoff.md
```

Metrics:

```text
success rate
reward
cost
latency
tokens
test pass rate
human review rate
review burden
context tokens
failure class
```

### Tests

```text
test_bakeoff_report_schema
test_bakeoff_runs_multiple_agents_or_marks_unavailable
test_bakeoff_has_failure_taxonomy
```

### Acceptance

Bakeoff generates data useful for routing decisions.

---

## Day 2, Block 5 — Stress and soak hardening

### Tasks

Upgrade `run_soak.py`:

1. Track:

```text
RSS memory
open file descriptors
workspace dirs
git worktree list
artifact bytes
DB rows
status distribution
p50/p95 latency
policy arm stats
```

2. Add thresholds:

```text
no orphan worktrees
memory growth < 25%
failure rate explained
artifact growth bounded
```

3. Output:

```text
evals/reports/soak.json
evals/reports/soak.md
```

4. Add `--iterations`, `--hours`, `--concurrency`, `--task-mix`, `--seed`.

5. Add concurrent workflow test:

```text
100 workflows
same repo
unique workspaces
no DB corruption
```

### Tests

```text
test_soak_report_schema
test_concurrent_workflows_isolated
test_no_orphan_worktrees_after_soak
```

### Acceptance

The soak test produces actionable operational signals.

---

## Day 2, Block 6 — Real adapter readiness

### Tasks

1. Add adapter health API:

```text
GET /agents
GET /agents/{name}/health
```

2. Add live-test skeletons:

```text
tests/live/test_openai_adapter.py
tests/live/test_claude_adapter.py
tests/live/test_codex_adapter.py
tests/live/test_openhands_adapter.py
```

3. Mark live tests skipped unless required env vars/binaries are present.
4. For real adapters, assert:

```text
healthcheck explains unavailable reason
workspace containment
token capture
diff capture
timeout handling
budget handling
no secret leakage
```

5. Make Claude/Codex/OpenHands adapters explicit about whether they are true harness adapters or simple model adapters.

### Acceptance

Live adapter tests are safe, optional, and informative.

---

## Day 2, Block 7 — CLI/API inspection polish

### CLI commands to add or finish

```bash
acp repo add <path>
acp repo index <repo-id>
acp task create --repo <repo-id> --title ... --body ...
acp run start <task-id>
acp run status <run-id>
acp run graph <run-id>
acp run trace <run-id>
acp run diff <run-id>
acp run evidence <run-id>
acp run evaluation <run-id>
acp reviews show <review-id>
acp reviews label <review-id> --verdict pass|fail --reason ...
acp agents list
acp agents health <name>
acp policy train
acp policy promote <policy-id>
acp policy rollback <policy-id>
acp eval context-benchmark
acp eval bakeoff
```

### Tests

```text
test_cli_full_lifecycle
test_cli_run_graph_after_restart
test_cli_review_label_resumes_run
test_cli_agents_health
```

### Acceptance

A user can operate the full local product through CLI only.

---

## Final acceptance criteria for the two-day push

At the end of this work, require:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
make coverage
make test-e2e
make retriever-stress
make security-redteam
make bandit-monte-carlo
```

And produce these reports:

```text
evals/reports/context_benchmark.json
evals/reports/bakeoff.json
evals/reports/soak.json
CURRENT_STATUS.md
IMPLEMENTATION_LOG.md
```

Minimum acceptance:

```text
1. Full run graph reconstructs after service restart.
2. Crash-resume works after every workflow node.
3. Human-review resume works after restart.
4. Command records persist.
5. Weak labels persist and influence human-review decisions.
6. Live bandit policy updates in main workflow.
7. Candidate routing decisions include multiple candidates and propensities.
8. Docker workspace exists or is cleanly skipped with tests.
9. Context benchmark reports recall@k and latency.
10. Bakeoff report compares at least fake/patch and marks unavailable real adapters.
11. Soak report includes memory/workspace/artifact/DB metrics.
12. API and CLI expose graph/trace/diff/evidence/evaluation.
```

## Highest-leverage next move

Start with **full persistent run graph + real crash-resume tests**. Everything else—real agents, better routing, context benchmarking, active learning, post-merge outcomes—depends on the system being able to trust and replay its own history.
