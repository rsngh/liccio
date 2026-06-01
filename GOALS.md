## Executive assessment

I evaluated the newer sprint branch, **`feat/acp-round1-twoday`**, because your sprint report says the ambitious round-1 work landed there. I did not independently execute the test suite in a checkout, so I’m treating the test-count and live-experiment claims as **reported until CI confirms them**.

This is now a **serious alpha** of the agent-control-plane concept. It is no longer just a scaffold. It has a real core loop, persistent provenance, crash-resume tests, a fuller CLI/API, an evaluation pipeline, adaptive routing primitives, Docker workspace v1, vector-store abstractions, context benchmarks, bakeoff, and soak reporting.

I would **open a PR, not merge directly yet**. The branch deserves review and CI validation because the docs currently disagree: `CURRENT_STATUS.md` says 179 tests and ~84% coverage, `FINAL_REPORT.md` still says 151 tests and ~83% coverage, and your sprint report says 222 tests. That inconsistency should be fixed before merging.   

---

# What has been implemented

## 1. Honest product status

This is much improved. `CURRENT_STATUS.md` now explicitly says this is a **local v0 / alpha, not production-grade**, and calls out that external harnesses, container isolation, and managed retrieval/observability backends are still optional or partial. That is the right framing. 

## 2. Core control-plane loop

The branch now claims and implements a durable control-plane loop: task → context → route → attempt → verify → evaluate → human review → reward → learn. `CURRENT_STATUS.md` describes this as a durable 16-node `WorkflowRunner`. 

The current runner also imports active learning, weak supervision, fake LLM judges, persisted span records, policy injection, and verification runs, indicating that the live loop is much richer than the earlier heuristic/objective-only version. 

## 3. Persistent run state and provenance

The data model now includes the entities needed for a real experience graph: repo snapshots, context packs, routing decisions, attempts, diffs, verification runs, evidence, evaluation results, human review, weak labels, reward events, post-merge outcomes, run states, spans, artifacts, and audit logs. 

`CURRENT_STATUS.md` says full provenance is persisted and reconstructable through `all_for_task`, including task, snapshot, context pack, plan, decision, attempts, diffs, verification runs, evidence, evaluation, weak label, reward, and spans. 

This is one of the biggest wins. The original product thesis depends on turning every agent run into training data; this branch finally has the right shape for that.

## 4. Durable resume / crash-resume

There is now an explicit crash-resume integration test. It stops after seven workflow nodes, discards the runner, creates a new `AppService`, reloads from the DB, resumes, and asserts success with no duplicate reward/finalization. 

There is also a test for crashing while waiting for human review: a fresh service lists reviews, applies a human label, resumes, and finalizes. 

This is very good. It is not yet exhaustive: the test covers seven nodes, not every node in the workflow. 

## 5. Command-runner hardening

The command runner now uses `Path.is_relative_to` containment, scrubs sensitive environment variables before launching child processes, supports output artifacting and redaction, kills process groups on timeout, records exit code/timing, and supports trace metadata.  

This directly addresses earlier concerns around string-prefix path escapes and env-secret leakage.

## 6. Docker workspace v1

The Docker manager is no longer just a stub. It uses the Docker CLI, creates a git worktree, and builds `docker run` commands with network disabled by default, memory/CPU/pid limits, a `/workspace` mount, working directory, and optional non-root user.  

This is a real sandbox primitive, but it still needs a stronger proof that the workflow actually executes untrusted verification/agent commands inside Docker end-to-end, not just constructs Docker arguments.

## 7. Evaluation pipeline

The new `EvaluationPipeline` bundles objective evaluation, weak supervision, LLM judges, active learning, and adversarial fraud detection into a single reusable component. 

It computes weak labels, runs judge inputs, scans diffs for adversarial findings, adjusts review burden, computes active-learning priority, and returns an evaluation bundle. 

That is a strong implementation of the “evaluation ladder” idea.

## 8. Adaptive routing primitives

The branch now has a `CandidateGenerator` that generates candidates over agents, context strategies, and verification policies while carrying forward the base action shape. 

`CURRENT_STATUS.md` says the live loop uses multi-agent candidates, constraints, a `SimulatedBanditPolicy`, candidate scores, and logged propensities. 

This is a major move toward the original routing thesis. The next step is making policy state durable across process restarts and replacing the simulated policy with production-grade contextual bandit backends.

## 9. Context compiler and retrieval benchmark

The context benchmark is now measurable. It generates synthetic repos, compiles context packs, and reports recall@5, recall@10, MRR, token count, latency, duplicate-chunk ratio, and secret leakage.  

The CLI wrapper writes JSON and Markdown reports. 

This is the right direction: context quality should be benchmarked, not eyeballed.

## 10. Vector-store abstraction

The branch has a `VectorStore` protocol and an always-available `InMemoryVectorStore`. It also has `PgVectorStore` and `QdrantStore` classes. 

However, pgvector and Qdrant currently fall back to an in-memory store rather than using real service-backed storage. 

So the abstraction exists, but production vector DB support is not done yet.

## 11. Bakeoff harness

The bakeoff harness now runs a matrix of task class, context strategy, verification policy, and seed, and emits a scorecard with success rate, human-review rate, latency, reward, agents used, unavailable adapters, and failure taxonomy.  

This is much better than the earlier toy bakeoff.

## 12. Soak harness

The soak harness now tracks operational metrics: RSS memory, open file descriptors, workspace dirs, artifact bytes, latency percentiles, status distribution, and policy arm stats.  

The wrapper writes JSON and Markdown reports. 

This is a strong start. True concurrency still appears reserved rather than implemented in the wrapper. 

## 13. CLI expansion

The CLI now includes repo management, task creation, run lifecycle and inspection, agent health, policy training/listing, review labeling, context benchmark, and bakeoff commands. The fetched CLI output is truncated, but the visible file clearly shows these command groups and handlers. 

---

# What has not been implemented or is still too thin

## 1. Real agent harnesses are still missing

This is the largest remaining gap. `CURRENT_STATUS.md` explicitly says Claude/OpenAI/Codex/OpenHands adapters are **simple model adapters** using a single JSON-edit prompt, not full tool-loop harnesses. 

The original plan was about routing between real coding agents and agent harnesses. Until at least one of Claude Agent SDK, Codex SDK, or OpenHands is implemented as a true harness with file/tool/command traces, this is still a control-plane alpha rather than a real multi-agent router.

## 2. Docker is v1, not yet proven as the default safe execution path

The Docker manager builds a good `docker run` command, but I would require tests proving actual workflow commands execute inside Docker. The current status still warns that local execution is not an OS-level sandbox. 

## 3. pgvector/Qdrant are not real backends yet

The protocol exists, but the pgvector and Qdrant classes use an in-memory fallback. 

That is fine for local tests, but docs and tests should avoid implying service-backed vector DB support until live integration tests prove it.

## 4. Crash-resume is not exhaustive

The crash-resume harness covers seven nodes and human-review pause. It should cover every workflow node, plus exception-after-persist failures. 

## 5. Docs and sprint numbers disagree

This needs cleanup before merge:

```text
CURRENT_STATUS.md: 179 tests, ~84% coverage.
FINAL_REPORT.md: 151 tests, ~83% coverage.
Sprint report: 222 tests, 2 docker skipped.
```

The docs should be regenerated from actual CI output.   

## 6. Evaluation is still mostly synthetic/fake-judge based

The pipeline is correctly structured, but fake judges and synthetic tasks dominate. The next stage should calibrate automated evaluators against human labels and real post-merge outcomes.

## 7. Bakeoff is still too deterministic

The bakeoff matrix is real, but many tasks are created with direct patch metadata pointing at the desired file content. 

That is useful for control-plane plumbing, but not enough to compare coding agents. Future bakeoffs need tasks without pre-supplied patches.

## 8. True concurrent stress is still unclear

The soak wrapper has a `--concurrency` argument, but it is marked reserved.  The underlying soak loop appears serial. 

A control plane needs to survive concurrent runs, DB contention, artifact contention, shared repo snapshots, and worktree cleanup races.

---

# Constructive feedback

## Open the PR, but don’t merge yet

Open the PR from `feat/acp-round1-twoday`. Do not merge until a PR validation gate passes.

Suggested PR labels:

```text
alpha
agent-control-plane
needs-ci
needs-security-review
do-not-merge-yet
```

## Make `CURRENT_STATUS.md` the source of truth

`CURRENT_STATUS.md` is much more accurate than `FINAL_REPORT.md`. Either update `FINAL_REPORT.md` completely or archive it as historical. Right now, it contains stale numbers and stale limitations. 

## Promote “real vs fallback” clarity

For each subsystem, explicitly mark:

```text
real local implementation
real service-backed implementation
simple adapter
true harness adapter
stub
fallback
```

This matters for vector stores and agent adapters especially.

## Put every claim behind a test artifact

The sprint report is strong, but the merge decision should rely on artifacts:

```text
pytest output
coverage output
alembic output
security-redteam report
context benchmark report
bakeoff report
soak report
bandit Monte Carlo report
live OpenAI report
```

## Make Docker mandatory for real agents

Local execution should remain for fake/patch/dev tests. Real LLM/code agents should default to Docker or Kubernetes.

Policy:

```text
fake/patch: local allowed
simple model adapter: Docker preferred
true harness adapter: Docker required unless explicitly overridden
network: denied by default
secrets: denied by default
```

## Make the next moat “real agent traces”

The next big leap is not adding more synthetic benchmarks. It is collecting normalized traces from real harnesses:

```text
Claude Agent SDK
Codex SDK
OpenHands
OpenAI model adapter baseline
patch/fake baseline
```

Same task, same repo, same context compiler, same verifier, same reward model.

---

# Tests to add beyond the current plan

## 1. PR validation gate

Run this in CI and attach the outputs:

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

The docs should be updated from these outputs.

## 2. Exhaustive crash-resume test

Expand the current seven-node test to every workflow node:

```text
stop_after_node=node
persist state
destroy service/runner
fresh AppService
resume
assert terminal status or expected human pause
assert no duplicate finalization
assert no duplicate reward
assert no duplicate evidence
assert run graph resolves
```

Also test:

```text
fail_after_node=node
exception after persist
resume/fail deterministically
```

## 3. Docker actual-execution tests

Do not only test Docker argv construction. Run real commands:

```text
pwd returns /workspace
id -u is non-root
curl fails with network none
memory hog is killed
fork bomb is contained
file created in Docker appears in workspace
diff captures Docker-created change
cleanup removes worktree
```

## 4. Local-vs-Docker parity

Run the same bugfix through both backends.

Assert:

```text
same final status
same changed files
same verification evidence
same no-secret guarantee
```

## 5. Harness truth tests

For every adapter:

```text
is_harness=true only if it captures tool/file/command traces
is_model_adapter=true if it only returns JSON edits
```

Fail if Claude/Codex/OpenHands are labeled as harnesses before they actually use their respective harness SDKs.

## 6. Vector DB live contract tests

For pgvector and Qdrant:

```text
connect to service
upsert vectors
query by vector
filter by snapshot_id
delete snapshot
restart client
query persists
```

If no service is configured, skip. Do **not** silently pass using in-memory fallback.

## 7. Retrieval adversarial benchmark

Extend synthetic repo generation with:

```text
decoy files
deprecated modules
same-symbol collisions
wrong tests
docs pointing to old paths
large generated files
secret-looking files
binary files
multi-language files
```

Measure:

```text
recall@5
recall@10
MRR
decoy false-positive rate
secret leakage
latency at 5k/25k/100k files
```

## 8. Evaluator fraud corpus

Add malicious patches that:

```text
delete tests
add pytest.skip
add xfail
weaken assertions
hardcode expected values
swallow exceptions
change test config
touch unrelated auth/billing files
only update snapshots
```

Expected behavior:

```text
tests may pass
evaluation flags suspicious
human review required
weak label persisted
reward penalized
```

## 9. True concurrent soak

Implement real concurrency and run:

```bash
uv run python evals/scripts/run_soak.py \
  --iterations 500 \
  --concurrency 8 \
  --task-mix bugfix,fail,human
```

Assert:

```text
no DB corruption
no duplicate run IDs
no branch/worktree collisions
no orphan worktrees
bounded RSS/FD growth
p95 latency reported
```

## 10. Post-merge outcome replay

Run a successful workflow, mark it merged, then ingest:

```text
revert
incident
issue reopened
high review rounds
```

Assert:

```text
matured negative reward created
policy observes negative outcome
run graph includes post-merge outcome
audit event exists
```

## 11. Real-agent live bakeoff

Optional/live:

```text
OpenAI simple adapter
Claude Agent SDK adapter
Codex SDK adapter
OpenHands adapter
```

Each must prove:

```text
token capture
diff capture
tool/command trace where applicable
budget stop
timeout stop
workspace containment
secret non-leakage
```

---

# Next two-day plan for an LLM coding agent

## Mission

Take this from **Alpha 1** to **Alpha 2: real-agent-ready control plane**.

The Alpha 2 bar:

```text
1. PR validation artifacts are generated and docs are consistent.
2. Crash-resume is exhaustive across workflow nodes.
3. Docker is proven as an actual execution backend.
4. Run graph is complete and API/CLI inspectable.
5. Eval reports become persisted product data.
6. At least one true agent harness adapter is implemented or started seriously.
7. Retrieval benchmarks are adversarial and scaled.
8. Concurrent soak is real.
```

---

## Day 1 — Validation, durability, sandboxing

### Block A — Reconcile docs and CI

Run:

```bash
mkdir -p reports
uv sync --all-extras
uv run pytest -q | tee reports/pytest.txt
uv run ruff check . | tee reports/ruff.txt
uv run mypy src | tee reports/mypy.txt
uv run alembic upgrade head | tee reports/alembic.txt
make coverage | tee reports/coverage.txt
```

Update:

```text
CURRENT_STATUS.md
FINAL_REPORT.md
IMPLEMENTATION_LOG.md
PR_CHECKLIST.md
```

Acceptance:

```text
All docs agree on test count and coverage.
No stale “future work” language remains for features now implemented.
```

### Block B — Full run graph schema

Create a `RunGraph` Pydantic schema with:

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
judge_results
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

to return full graph data, not only counts.

Tests:

```text
test_run_graph_schema
test_run_graph_after_restart
test_all_state_ids_resolve
test_artifacts_resolve
test_no_raw_secret_in_graph
```

### Block C — Exhaustive crash-resume

Expand crash-resume from seven nodes to all workflow nodes.

Tests:

```text
test_crash_after_every_node_then_resume
test_exception_after_every_node_no_corruption
test_waiting_for_human_without_label_stays_blocked
test_human_label_after_restart_finalizes_once
```

Acceptance:

```text
Every node is either resumable or explicitly marked non-resumable with a test.
```

### Block D — Docker execution backend

Implement actual Docker-backed command execution, not only Docker workspace creation.

Required behavior:

```text
CommandRunner detects Docker workspace or uses DockerCommandRunner.
Commands execute inside docker run.
Network none by default.
Non-root by default.
Memory/CPU/pid limits enforced.
Diff capture works from mounted workspace.
```

Tests:

```text
test_docker_command_pwd_is_workspace
test_docker_no_network
test_docker_nonroot
test_docker_memory_limit
test_docker_pids_limit
test_docker_diff_capture
test_local_docker_bugfix_parity
```

### Block E — Security red-team expansion

Add tests for:

```text
symlink escape
PATH injection
parent-dir read attempt
env exfiltration
network exfiltration
test deletion
verification config tampering
massive stdout
```

Acceptance:

```bash
make security-redteam
```

passes and searches DB/artifacts/logs/spans for raw fake secrets.

---

## Day 2 — Real evals, routing, harness readiness

### Block F — Persist eval reports

Add entities:

```text
EvalRun
EvalCase
EvalAttempt
EvalMetric
EvalReport
```

Wire these into:

```text
context benchmark
bakeoff
soak
bandit Monte Carlo
```

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
Eval reports are durable DB entities and can feed future policy training.
```

### Block G — Adversarial retrieval benchmark

Extend `generate_synthetic_repo` with:

```text
decoys
deprecated files
same-symbol collisions
wrong tests
old docs
generated files
secrets
binary files
mixed languages
```

Run at:

```text
1k files
5k files
25k files
100k chunks
```

Report:

```text
recall@5
recall@10
MRR
false-positive decoy rate
secret leakage
latency
token usage
duplicate ratio
```

Acceptance:

```text
Hybrid strategy beats keyword-only and embedding-only.
No secret leakage.
Latency reported.
```

### Block H — Real vector DB contracts

Implement true service-backed pgvector and Qdrant paths.

Tests:

```text
@pytest.mark.live_pgvector
@pytest.mark.live_qdrant
```

Each test must:

```text
connect
upsert
query
filter by snapshot
delete snapshot
reconnect
query persists
```

Acceptance:

```text
In-memory fallback is explicit.
Service-backed tests never pass by silently using memory.
```

### Block I — First true harness adapter

Pick one: **OpenHands** or **Claude Agent SDK**.

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

It must run in Docker by default.

Tests:

```text
test_harness_unavailable_cleanly
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

### Block J — Persisted routing policy state

Add:

```text
PolicyState
PolicyObservation
PolicyDriftReport
OffPolicyReport
```

Implement:

```text
arm stats persisted
policy state reloads after restart
reward observation persisted
IPS/SNIPS report persisted
drift detector persisted
```

Tests:

```text
test_policy_state_survives_restart
test_observe_reward_updates_persisted_arm
test_policy_selects_different_agent_after_training
test_ope_report_persisted
test_drift_detector_flags_reward_drop
```

### Block K — True concurrent soak

Implement real `--concurrency`.

Run:

```bash
uv run python evals/scripts/run_soak.py \
  --iterations 500 \
  --concurrency 8 \
  --task-mix bugfix,fail,human
```

Track:

```text
p50/p95/p99 latency
DB lock retries
workspace leaks
artifact leaks
RSS growth
FD growth
policy arm growth
failure taxonomy
```

Acceptance:

```text
No DB corruption.
No duplicate run IDs.
No orphan worktrees.
No unbounded RSS/FD growth.
```

### Block L — PR readiness artifacts

Commit or attach:

```text
reports/pytest.txt
reports/coverage.txt
evals/reports/context_benchmark.json
evals/reports/bakeoff.json
evals/reports/soak.json
PR_CHECKLIST.md
```

Acceptance checklist:

```text
[ ] docs/test counts consistent
[ ] CI green
[ ] full run graph reconstructs after restart
[ ] exhaustive crash-resume passes
[ ] Docker actual execution proven or explicitly skipped
[ ] security red-team passes
[ ] eval reports generated
[ ] real harness status truthful
[ ] no production-grade overclaim
```

---

# Merge recommendation

Open the PR now. Merge only after:

```text
1. CI confirms the actual 222-test claim or docs are corrected.
2. FINAL_REPORT.md and CURRENT_STATUS.md agree.
3. Exhaustive crash-resume covers all workflow nodes.
4. Docker is proven to execute commands, not only construct argv.
5. Run graph reconstruction is tested after restart.
6. Vector DB and harness claims are labeled accurately as real, fallback, or stub.
```

The sprint is a major leap. The next leap is turning this from a very good local alpha into a **trustworthy real-agent experimentation platform**: durable under crashes, safe under untrusted execution, measurable under load, and honest about which adapters are real harnesses versus simple model wrappers.
