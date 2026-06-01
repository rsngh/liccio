I evaluated the **round-1 branch referenced in the sprint report**, `feat/acp-round1-twoday`, rather than only the older `feat/agent-control-plane` URL. I inspected the implementation through GitHub, but I did **not** run the test suite locally, so I’m distinguishing “verified from source/docs” from claims that still need an independent CI run.

## Bottom line

This is now a **serious alpha**, not just a scaffold. The sprint delivered many of the highest-leverage primitives from the plan: durable run state, full provenance graph, live policy injection, weak supervision/eval pipeline, Docker workspace v1, vector-store protocol, crash-resume tests, context benchmarks, bakeoff reports, soak metrics, and a much fuller CLI.

I would **open a PR**, not merge directly yet. The branch should go through a hard validation gate because several claims are still either partially implemented, lightly tested, or internally inconsistent in the docs. For example, `CURRENT_STATUS.md` says 179 tests pass and ~84% coverage, while `FINAL_REPORT.md` still references 151 tests and ~83% coverage, and your sprint report says 222 tests pass. Those need to be reconciled before merge.   

---

# What has been implemented

## 1. Honest alpha positioning

This is fixed in the right direction. `CURRENT_STATUS.md` explicitly says this is a **local v0 / alpha, not production-grade**, and calls out that external agent harnesses, container isolation, and managed retrieval/observability backends are optional or partially stubbed. 

That is exactly the right posture. The previous “production-grade” language was premature; this version is more credible.

## 2. Core control-plane loop

The status file claims the core loop is implemented as a durable 16-node `WorkflowRunner`: task, context, routing, agent attempt, verification, evaluation, human review, reward, and learning. 

The workflow runner source also shows the architecture has moved from a simpler 15-node loop to a richer loop including `score_signals`, and imports weak supervision, active learning, fake judges, span records, policy injection, and verification runs. 

## 3. Persistent data model and provenance

The data model is now much closer to the original plan. It includes tables for repository/task/context/routing/attempt/diff/verification/evidence/evaluation/human-label/weak-label/reward/policy/post-merge artifacts, and now also includes `run_states` and `spans`. 

`CURRENT_STATUS.md` claims full provenance is persisted for task, snapshot, context pack, plan, routing decision, attempts, diffs, verification runs, evidence, evaluation, weak label, reward, and spans. 

This is one of the biggest wins of the sprint.

## 4. Durable resume and crash-resume harness

This is materially improved. The branch now includes an integration test that injects a stop after seven workflow nodes, discards the runner, constructs a fresh `AppService`, reloads from the DB, resumes, and asserts no duplicate finalization or reward. 

It also tests crash/resume while waiting for human review: a new service lists reviews, labels the review, resumes, and finalizes. 

Important nuance: this tests seven resumable nodes, not every node in the workflow. It is a good harness, but not yet exhaustive.

## 5. Command-runner hardening

The command runner is much stronger. It now uses `Path.is_relative_to` for cwd containment, supports secret scrubbing from the child process environment, still handles process-group timeouts, stdout/stderr redaction, artifact storage, and trace metadata.  

This addresses one of the earlier serious issues: string-prefix cwd checks.

## 6. Docker workspace v1

Docker is no longer just a stub. The new `DockerWorkspaceManager` uses the Docker CLI, creates a local git worktree, and can construct `docker run` commands with `--network none`, memory limits, CPU limits, pid limits, a `/workspace` mount, working directory, and optional non-root user.  

This is a real v1 sandbox primitive. It is not yet a full production sandbox, but it is a big step.

## 7. Evaluation pipeline

The branch now has a single `EvaluationPipeline` that bundles objective evaluation, weak supervision, LLM judges, active learning, and adversarial fraud detection into one reusable unit. 

It computes weak labels, runs fake LLM judges, scans diffs for adversarial findings, adjusts review burden, computes active-learning priority, and returns an `EvaluationBundle`. 

This is a strong implementation of the “evaluation ladder” idea.

## 8. Adaptive routing primitives

The routing layer now has a `CandidateGenerator` that generates actions across agents, context strategies, and verification policies, carrying through the base action’s risk/budget shape. 

`CURRENT_STATUS.md` claims the live loop uses multi-agent candidates, constraints, and `SimulatedBanditPolicy`, logging candidates/scores/propensity. 

This is much closer to the product thesis than the previous heuristic-only implementation.

## 9. Context retrieval benchmark

There is now a retrieval benchmark runner that generates a synthetic repo, runs retrieval, and emits JSON/Markdown reports. 

The benchmark measures recall@5, recall@10, MRR, token count, compile latency, duplicate-chunk ratio, and secret leakage.  

This is a big improvement: context quality is now measurable rather than just asserted.

## 10. Vector-store protocol

The branch now includes a `VectorStore` protocol and `InMemoryVectorStore`, plus `PgVectorStore` and `QdrantStore` classes. However, the pgvector and Qdrant classes currently fall back to in-memory behavior rather than implementing real service-backed storage.  

So the protocol is implemented, but managed vector DB integration remains partial.

## 11. Bakeoff harness

The new bakeoff harness runs a matrix of task class, context strategy, verification policy, and seed, producing a machine-readable scorecard with success rate, human-review rate, mean reward, agents used, unavailable adapters, and failure taxonomy.  

This is a major improvement over the earlier toy bakeoff.

## 12. Soak harness

The soak harness now tracks operational metrics: RSS memory, file descriptors, workspace dirs, artifact bytes, latency percentiles, status distribution, and policy arm stats.  

The CLI wrapper writes JSON and Markdown reports. 

## 13. CLI expansion

The CLI is now much closer to a real local product. It includes repo add/list/index, task create, run start/status/graph/trace/diff/evidence/evaluation, agents list/health, policy train/list, reviews list/show/label, context benchmark, and bakeoff commands. 

The fetched CLI file is truncated in the tool output, but the visible content clearly shows these command groups and implementations.

---

# What has not been implemented or is still too thin

## 1. Full coding-agent harnesses are still not there

The status file is refreshingly honest: Claude/OpenAI/Codex/OpenHands adapters are described as **simple model adapters using a single JSON-edit prompt**, not full tool-loop harnesses. 

This remains the largest product gap. The original thesis was about routing between real coding agents and harnesses. Until Claude Agent SDK, Codex SDK, and OpenHands SDK are wrapped as true interactive agents with tool traces, command execution, file reads/writes, permissions, and budget control, this is not yet a true multi-agent coding-agent router.

## 2. Docker v1 exists, but hard sandboxing is not done

Docker v1 can construct a secure-ish `docker run` command, but the status file still says container isolation is partial, and local command execution is not an OS-level sandbox. 

The Docker manager builds run arguments, but I did not see full orchestration integration proving every untrusted command actually runs through Docker rather than the local `CommandRunner`. That should be validated hard.

## 3. pgvector/Qdrant are protocol-level, not real backends

`PgVectorStore` and `QdrantStore` currently wrap an in-memory store. The code comments say real pgvector wiring lands when a Postgres+pgvector DSN is configured. 

So the abstraction is good, but production retrieval infrastructure remains future work.

## 4. Crash-resume coverage is not exhaustive

The new crash-resume test covers seven nodes: `classify_task`, `compile_context`, `route_task`, `launch_agent_attempts`, `run_verification`, `evaluate_attempt`, and `score_signals`. 

That is a solid start, but the workflow has more nodes. It should test every node, including snapshot creation, verification-plan generation, diff capture, evidence aggregation, human-review decision, reward computation, policy update, and finalize.

## 5. The docs are inconsistent

`CURRENT_STATUS.md` says 179 tests and ~84% coverage. `FINAL_REPORT.md` still says 151 tests and ~83% coverage, and still contains older limitations about cross-process resume even though the newer code and tests now show a resume implementation.   

Your sprint report says 222 tests. Before merge, make the docs and CI artifact agree.

## 6. Evaluation is still synthetic-heavy

The evaluation pipeline is integrated, but fake judges and synthetic fixtures dominate. That is fine for deterministic CI, but the next milestone must add calibrated real LLM judges, human-label calibration, adversarial test corpora, and post-merge outcome replay.

## 7. Bakeoff is useful but still too deterministic

The bakeoff matrix is real, but it still creates deterministic tasks with `metadata={"files": {"calculator.py": FIXED_CALC}}`, which means the patch adapter path is highly privileged and not representative of real coding-agent behavior. 

The next bakeoff should include tasks where no patch is pre-specified, tasks with ambiguous specs, multi-file dependencies, failing tests, and real-agent attempts.

## 8. Soak is better, but concurrency is not implemented

`run_soak.py` has a `--concurrency` flag, but it is marked “reserved.” 

The core `run_soak` implementation loops serially. 

For a control plane, concurrency is not optional. The next stress pass needs true concurrent workflows, shared repo snapshots, DB contention, artifact contention, and worktree cleanup checks.

---

# Constructive feedback

## Open the PR, do not merge yet

Open the PR from `feat/acp-round1-twoday`. Do not merge into `feat/agent-control-plane` until you have:

```text
1. A fresh CI run showing the actual test count.
2. Updated CURRENT_STATUS.md and FINAL_REPORT.md with the same numbers.
3. A merge checklist proving Docker, crash-resume, provenance graph, and CLI/API gates.
4. A note that real harness adapters remain simple model adapters for now.
```

## Treat this as “Alpha 1”

This branch now deserves a version label:

```text
ACP Alpha 1:
  local no-key loop
  persistent run graph
  crash-resume harness
  Docker sandbox v1
  eval pipeline
  live simulated bandit
  context benchmark
  bakeoff/soak reports
```

That is a clean milestone.

## Make the next moat “real traces from real agents”

The product moat comes from real-world agent experience on codebases. The next step is not another local simulation. The next step is:

```text
same tasks
same repo
Claude Agent SDK vs Codex SDK vs OpenHands vs OpenAI model adapter vs patch/fake baseline
same trace schema
same verifier
same cost accounting
same reward/eval pipeline
```

That will turn this from a control-plane prototype into an empirical routing product.

## Promote “report artifacts” to first-class product data

Context benchmark, bakeoff, soak, and bandit Monte Carlo reports should not just write files. They should become first-class entities:

```text
EvalRun
EvalCase
EvalAttempt
EvalReport
EvalMetric
```

Then the router can train from them.

## Be stricter about “real” vs “fallback”

The current vector-store file says pgvector and Qdrant are “real when available,” but the methods currently fall back to in-memory behavior. 

I would rename them until they are truly service-backed:

```text
PgVectorStoreAdapterSkeleton
QdrantStoreAdapterSkeleton
```

or make `.available()` return false unless a working service connection is configured and tested.

---

# Tests to add beyond the specified ones

## 1. Independent merge-gate test

Run this exact command in CI and save the output artifact:

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make test-e2e
make security-redteam
make bandit-monte-carlo
make retriever-stress
```

Then update docs from the actual output.

## 2. Exhaustive crash-resume matrix

Expand from seven nodes to every node in `NODE_ORDER`.

For each node:

```text
stop_after_node=node
persist
destroy service/runner
construct fresh service
resume
assert terminal status
assert one reward event
assert one finalize
assert no duplicate attempts
assert no duplicate evidence
assert run graph resolves
```

The current test is good but covers only a subset. 

## 3. Docker execution proof

Test not only that Docker argv is constructed, but that commands actually run in Docker:

```text
pwd returns /workspace
id -u is not 0 when non-root enabled
network request fails when allow_network=false
memory hog is killed
fork bomb is contained by pids limit
created files appear in mounted workspace
diff capture sees Docker-created changes
cleanup removes worktree
```

## 4. Local-vs-Docker parity test

Run the same bugfix workflow in local and Docker backends.

Assert:

```text
same final status
same changed files
same verification status
same evidence kinds
same no-secret property
```

## 5. Agent harness truth tests

For every adapter, classify:

```text
is_harness = true only if it supports tool-loop/file/command traces
is_model_adapter = true if it only returns JSON edits
```

Fail the test if Claude/Codex/OpenHands are called harnesses before they actually capture tool-loop traces.

## 6. Real vector DB contract tests

For pgvector and Qdrant, add live optional tests:

```text
insert 100 vectors
query exact/gold vector
filter by snapshot_id
delete snapshot
verify records gone
restart service/client
query still works
```

Skip if DSN/service unavailable. Do not silently fall back to memory in a test that claims to test pgvector or Qdrant.

## 7. Retrieval adversarial benchmark

Extend `generate_synthetic_repo` with:

```text
decoy files with similar names
duplicated symbols
old/deprecated modules
test fixtures containing same tokens
README references to wrong module
secret-looking files
large generated files
```

Measure:

```text
gold recall@5/@10
decoy false-positive rate
secret leakage
latency at 5k/25k/100k files
```

## 8. Evaluator fraud corpus

Add malicious patch cases:

```text
delete tests
add pytest.skip
add xfail
weaken assertions
hardcode test input
broad except
remove type check config
change pyproject to skip tests
snapshot-only update
unrelated auth/billing changes
```

Expected:

```text
tests may pass
evaluation must flag suspicious/human-review
reward must be lower than clean fix
weak label must persist
```

## 9. True concurrent soak

Implement `--concurrency`.

Run:

```bash
uv run python evals/scripts/run_soak.py --iterations 500 --concurrency 8
```

Assert:

```text
unique run IDs
unique workspaces
no DB lock failures
no duplicate branches
no orphan worktrees
memory growth under threshold
p95 latency bounded
```

## 10. Off-policy evaluation sanity suite

Synthetic logged data with known propensities:

```text
random policy
biased policy
missing propensity
zero propensity
high variance rewards
```

Assert IPS/SNIPS behavior and confidence intervals.

## 11. Post-merge outcome replay

Run a workflow, mark it merged, then ingest:

```text
revert
incident
issue reopened
review rounds
```

Assert:

```text
new matured reward event
policy observes negative outcome
run graph includes post-merge outcome
audit event created
```

## 12. End-to-end real-agent bakeoff

Optional live gate:

```bash
pytest -m live tests/live/test_openai_adapter.py
pytest -m live tests/live/test_claude_adapter.py
pytest -m live tests/live/test_codex_adapter.py
pytest -m live tests/live/test_openhands_adapter.py
```

Each must prove:

```text
token capture
diff capture
tool/command trace where applicable
budget stop
timeout stop
workspace containment
no secret leakage
```

---

# Detailed next-step plan for the next LLM coding agent

Below is the next ambitious, rigorous two-day sprint. This assumes `feat/acp-round1-twoday` is the starting branch.

## Sprint goal

Take ACP from **Alpha 1** to **Alpha 2: real-agent-ready control plane**.

The Alpha 2 bar:

```text
1. All round-1 claims independently validated.
2. Docker is the default backend for untrusted/live agents.
3. Crash-resume is exhaustive.
4. Reports are first-class persisted eval artifacts.
5. Real adapter harness interfaces are implemented or truthfully marked as model-only.
6. Retrieval benchmarks include adversarial and scale cases.
7. Concurrency soak is real.
8. Docs and CI are consistent.
```

---

## Day 1 — Validation, durability, sandboxing

### Block A — Reconcile and validate the branch

Run:

```bash
uv sync --all-extras
uv run pytest -q | tee reports/pytest.txt
uv run ruff check . | tee reports/ruff.txt
uv run mypy src | tee reports/mypy.txt
uv run alembic upgrade head | tee reports/alembic.txt
make coverage | tee reports/coverage.txt
```

Then update:

```text
CURRENT_STATUS.md
FINAL_REPORT.md
IMPLEMENTATION_LOG.md
```

with the actual numbers. Resolve the 151/179/222 test-count inconsistency.

Acceptance:

```text
Docs all cite the same test count and coverage.
CI artifacts are committed or attached to PR.
No stale “cross-process resume is future work” language if resume is now implemented.
```

---

### Block B — Full provenance graph hardening

Add a `RunGraph` Pydantic schema.

It should contain:

```text
state
task
repo
snapshot
context_pack
routing_decision
attempts
diffs
verification_plan
verification_runs
evidence
evaluation
weak_labels
judge_results or judge evidence
human_review_items
human_labels
reward_events
post_merge_outcomes
spans
audit_events
artifacts
```

Update:

```text
GET /runs/{run_id}/graph
acp run graph <run_id>
```

to return the full graph, not just counts.

Tests:

```text
test_full_run_graph_schema
test_run_graph_after_restart
test_all_workflow_state_ids_resolve
test_artifact_refs_resolve
test_no_raw_secret_in_run_graph
```

Acceptance:

```text
Given only DB + artifact dir + run_id, graph reconstructs completely.
```

---

### Block C — Exhaustive crash-resume

Expand `RESUMABLE_NODES` from seven nodes to all nodes that can safely persist.

For each node:

```text
stop_after_node
fresh AppService
resume_run
assert terminal or WAITING_FOR_HUMAN as appropriate
assert graph integrity
assert no duplicate reward/finalize/evidence/attempts
```

Also add failure injection:

```text
fail_after_node
simulate exception after persistence
resume or fail deterministically
```

Tests:

```text
test_crash_after_every_node_then_resume
test_exception_after_every_node_no_corruption
test_waiting_for_human_no_label_does_not_finalize
test_human_label_after_restart_finalizes_once
```

Acceptance:

```text
Every workflow node is crash-safe or explicitly marked non-resumable with a test.
```

---

### Block D — Docker as real execution backend

Implement a `DockerCommandRunner` or route `CommandRunner` through Docker when workspace backend is Docker.

Current `DockerWorkspaceManager` builds `docker run` argv; now make workflows actually execute verification/agent commands inside Docker when configured. 

Add config:

```text
ACP_WORKSPACE_BACKEND=local|docker
ACP_DOCKER_IMAGE=python:3.11-slim
ACP_DOCKER_NETWORK=none
ACP_DOCKER_MEMORY_MB=1024
ACP_DOCKER_CPUS=1
ACP_DOCKER_PIDS_LIMIT=256
```

Tests:

```text
test_docker_command_runner_pwd_is_workspace
test_docker_no_network_blocks_curl
test_docker_nonroot
test_docker_memory_limit
test_docker_pids_limit
test_docker_diff_capture
test_local_and_docker_bugfix_parity
```

Acceptance:

```text
When ACP_WORKSPACE_BACKEND=docker, untrusted commands run in Docker, not local subprocesses.
```

---

### Block E — Security red-team expansion

Add tests for:

```text
symlink escape
hardlink escape where supported
PATH injection
shell metacharacters in argv
attempt to read parent directory
attempt to print env secrets
attempt to use network
attempt to modify verification config
attempt to delete tests
attempt to write massive stdout
```

Acceptance:

```text
make security-redteam passes locally and in CI.
No raw fake secret appears in DB, artifacts, logs, spans, or reports.
```

---

## Day 2 — Real evals, real routing, real reports

### Block F — Persist eval reports as entities

Add schemas/tables:

```text
EvalRun
EvalCase
EvalAttempt
EvalMetric
EvalReport
```

Wire:

```text
context benchmark
bakeoff
soak
bandit monte carlo
```

to persist these, not just write JSON/Markdown files.

API:

```text
POST /evals/context-benchmark
POST /evals/bakeoff
POST /evals/soak
GET /evals/runs
GET /evals/runs/{id}
GET /evals/runs/{id}/report
```

CLI:

```bash
acp eval list
acp eval show <eval-run-id>
```

Acceptance:

```text
Reports are durable product data and can feed router training.
```

---

### Block G — Adversarial retrieval benchmark

Extend the retrieval benchmark generator with:

```text
decoy modules
deprecated modules
similar symbol names
wrong tests
docs pointing to old paths
large generated files
secrets
binary files
multi-language files
```

Metrics:

```text
recall@5
recall@10
MRR
false-positive decoy rate
secret leakage
latency
tokens
duplicate ratio
```

Run at:

```text
1k files
5k files
25k files
100k chunks
```

Acceptance:

```text
Hybrid strategy beats keyword-only and embedding-only on recall/MRR.
No secret leakage.
Latency reported.
```

---

### Block H — Real vector DB live tests

Implement real pgvector and Qdrant paths behind optional live tests.

Do not let “pgvector test” silently use in-memory fallback.

Tests:

```text
@pytest.mark.live_pgvector
@pytest.mark.live_qdrant
```

Each must test:

```text
connect
upsert
query
filter by snapshot_id
delete snapshot
restart client
query persists
```

Acceptance:

```text
InMemory remains default.
PgVector/Qdrant are truly service-backed when configured.
Fallbacks are explicit and visible.
```

---

### Block I — First true agent harness adapter

Pick one real harness first. I would start with **OpenHands** or **Claude Agent SDK**, because a real harness needs file/tool/command trace capture.

Adapter must capture:

```text
session_id
model
tool calls
file reads
file writes
commands
stdout/stderr refs
diff
tokens
cost
wall time
timeout
budget stop
errors
```

It must run only in Docker unless explicitly allowed.

Tests:

```text
test_harness_health_unavailable_cleanly
test_harness_live_tiny_bugfix
test_harness_captures_tool_calls
test_harness_captures_file_writes
test_harness_respects_budget
test_harness_no_secret_leak
```

Acceptance:

```text
At least one adapter is a true harness, not a JSON-edit model adapter.
```

---

### Block J — Routing policy alpha

Upgrade routing from simulated-bandit-in-process to persisted policy state.

Implement:

```text
PolicyState table/entity
arm stats persisted
policy snapshot load/save
reward observation persisted
off-policy report persisted
drift report persisted
```

Tests:

```text
test_policy_state_survives_service_restart
test_policy_observe_reward_updates_persisted_arm
test_policy_selects_different_agent_after_training
test_ips_snips_report_persisted
test_drift_detector_flags_reward_drop
```

Acceptance:

```text
The router learns across process restarts.
```

---

### Block K — True concurrent soak

Implement real concurrency in `run_soak.py`.

Use:

```text
asyncio tasks or multiprocessing
per-run DB sessions
shared repo snapshot
unique workspace dirs
thread/process-safe artifact writes
```

Run:

```bash
uv run python evals/scripts/run_soak.py \
  --iterations 500 \
  --concurrency 8 \
  --task-mix bugfix,fail,human
```

Metrics:

```text
p50/p95/p99 latency
DB lock retries
workspace leaks
artifact leaks
memory growth
FD growth
policy arm growth
failure taxonomy
```

Acceptance:

```text
No DB corruption.
No orphan worktrees.
No duplicate run IDs.
No unbounded RSS/FD growth.
```

---

### Block L — PR-readiness gate

Create `PR_CHECKLIST.md`:

```text
[ ] docs/test counts consistent
[ ] CI green
[ ] full graph reconstructs
[ ] exhaustive crash resume passes
[ ] security red-team passes
[ ] Docker backend tested or skipped explicitly
[ ] vector DB live tests skipped unless configured
[ ] eval reports generated
[ ] no production-grade overclaim
[ ] known risks listed
```

Generate and commit:

```text
evals/reports/context_benchmark.json
evals/reports/bakeoff.json
evals/reports/soak.json
reports/pytest.txt
reports/coverage.txt
```

Acceptance:

```text
The PR can be reviewed without trusting verbal claims.
```

---

# Merge recommendation

Open the PR now from `feat/acp-round1-twoday`, but label it:

```text
alpha
control-plane
needs-validation
do-not-merge-until-ci
```

I would merge only after:

```text
1. Test-count and coverage docs are reconciled.
2. Full CI passes on the PR.
3. Exhaustive crash-resume is expanded beyond seven nodes.
4. Docker backend is proven to execute commands, not only build argv.
5. The run graph is verified after process restart.
6. CURRENT_STATUS.md is the source of truth and FINAL_REPORT.md is updated or archived.
```

The sprint is a meaningful leap. The next leap is to make the system trustworthy under failure, concurrency, untrusted execution, and real agent harnesses.
