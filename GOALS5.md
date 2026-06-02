## Executive assessment

The current `feat/agent-control-plane` branch has reached a **credible Alpha 4**: it now implements the core architecture of a multi-harness empirical routing control plane. The biggest architectural gap from the previous review—“no true harness”—is materially addressed. There are now two true tool-loop harnesses claimed in the sprint report, and the branch contains a `ClaudeHarnessAdapter` plus the earlier `OpenAIHarnessAdapter`, both built around normalized tool-loop execution and trace capture. The attached sprint report says Round 4 completed with 329 passing tests, live OpenAI + Claude harness experiments, and a two-harness bakeoff. 

I would **open the PR now**, but I would **not merge until a short cleanup/validation pass** fixes stale status docs and attaches/commits the live harness evidence in a way reviewers can verify without trusting the sprint report.

The branch’s committed pytest artifact reports **329 passed, 5 skipped, 1 warning**, with ruff and mypy clean across 125 source files.  Coverage is now **86%**.  That is a substantial improvement over earlier rounds.

---

# What has been implemented

## 1. The Alpha 4 control-plane loop is now real enough to evaluate

The project now has the right shape for the original thesis: same task, same repo, same context, multiple harnesses, normalized traces, verification, calibrated evaluation, and learned routing. `ALPHA4_CHECKLIST.md` explicitly frames Alpha 4 around that goal and lists the new blocks: second harness, backend governance, mandatory `AgentTrace`, Docker evidence pack, no-patch bakeoff, bakeoff-to-router replay, and evaluator calibration. 

The core loop and provenance stack are still documented as implemented in `CURRENT_STATUS.md`: task → context → route → attempt → verify → evaluate → human review → reward → learn, with persisted task/snapshot/context/decision/attempt/diff/evidence/evaluation/weak-label/reward/spans. 

## 2. Test and coverage gates improved

The branch now carries committed test artifacts showing:

```text
329 passed, 5 skipped, 1 warning
ruff clean
mypy clean
125 src files
86% coverage
```

That evidence is in `reports/pytest.txt` and `reports/coverage.txt`.  

This resolves the earlier 151/179/222 ambiguity at the report-artifact level, but `CURRENT_STATUS.md` still says 305 tests and ~85%, so docs remain stale. 

## 3. Exhaustive crash-resume exists

This is one of the strongest parts of the branch.

`test_crash_resume_exhaustive.py` parametrizes over every workflow node except `finalize_run`, tests crash-after-node resume, tests exception-after-node resume, verifies clean finalization, and asserts no duplicate rewards. It also checks that waiting for human review does not finalize without a label, and that human labeling after restart finalizes exactly once.  

That is exactly the kind of reliability invariant this product needs.

## 4. Full run graph and merge-gate checks exist

The merge-gate test checks for no production-grade overclaim, reconstructs a full run graph after restart, and verifies migrations apply cleanly.  

The DB model includes `run_states`, `spans`, `policy_states`, `agent_traces`, and eval-report tables. 

The service layer persists richer run artifacts, including command runs, verification runs, evidence, weak labels, rewards, spans, and agent traces, and restores learned policy arms from persisted policy state on service startup. 

## 5. Two true harness classes now exist

The earlier `OpenAIHarnessAdapter` is a genuine ACP-managed tool-loop harness: it exposes `read_file`, `write_file`, `run_command`, and `finish`, captures tool calls, file writes, command records, diff, tokens, cost, wall time, and budget/timeout behavior. 

Round 4 adds `ClaudeHarnessAdapter`, which is explicitly described as the second true harness. It uses Anthropic tool-use, has `is_harness=True`, captures normalized trace data, enforces wall/cost/step budgets, and uses shared harness infrastructure so Claude and OpenAI traces are comparable.  

This is a major milestone.

## 6. Shared harness core is the right abstraction

`harness_base.py` is one of the best design choices in the branch. It centralizes workspace-contained tools, shared prompts, tool dispatch, consistent status semantics, and normalized result creation. 

That avoids each provider adapter inventing its own execution semantics. This matters because the product’s routing policy needs fair comparisons across harnesses.

## 7. Normalized `AgentTrace` is implemented

`AgentTrace` now captures the normalized cross-adapter trace surface: attempt ID, task ID, adapter name, harness flag, model, session ID, status, tool-call count, file reads/writes, commands, changed files, diff lines, tokens, cost, wall time, error, and metadata. 

This is the core data structure for agent routing. It lets you compare patch/fake/simple model adapters and true tool-loop harnesses in one schema.

## 8. Docker command execution and backend governance are in place

`DockerCommandRunner` executes commands inside `docker run`, while the host Docker invocation itself goes through the mediated `CommandRunner` for timeout/output/redaction capture. 

The Docker runner records the logical in-container command and marks resource usage with the Docker backend. 

Governance now says fake/patch can run locally, simple model adapters prefer Docker, and true harness adapters require Docker unless an explicit audited override is granted. 

This is the right security posture.

## 9. Vector store status is clearer

The vector layer now has:

```text
InMemoryVectorStore: real local
QdrantStore: real qdrant_client-backed engine
PgVectorStore: explicit memory fallback unless DSN/deps configured
```

Qdrant supports collection creation, upsert, query with snapshot filtering, and delete-by-snapshot. 

pgvector remains incomplete, but the fallback is visible through `backend = "memory-fallback"` when not configured. 

## 10. Evaluator calibration exists

The calibration module reports accuracy, Brier score, correlation, and per-source accuracy against human or post-merge truth.  

This is exactly what is needed to move from “weak supervision exists” to “we know when to trust it.”

## 11. Alpha 4 checklist captures the right acceptance criteria

The new `ALPHA4_CHECKLIST.md` has the right merge gates: two true harnesses, Docker governance, mandatory `AgentTrace`, no-patch bakeoff, bakeoff replay into router, and calibration thresholding. 

---

# What has not been implemented or still needs work

## 1. `CURRENT_STATUS.md` is stale and contradicts Alpha 4

This is the most immediate cleanup item.

`CURRENT_STATUS.md` still says:

```text
Tests: 305 passing
Real agent harnesses are simple model adapters
Docker v1 in progress
Managed services partially stubbed
```

But the Alpha 4 checklist and code show 329 tests, `ClaudeHarnessAdapter`, `OpenAIHarnessAdapter`, `DockerCommandRunner`, `AgentTrace`, Qdrant, and persisted evals.   

Since `FINAL_REPORT.md` says `CURRENT_STATUS.md` is the source of truth, this mismatch is PR-review friction. 

## 2. `FINAL_REPORT.md` still has stale historical content

The top of `FINAL_REPORT.md` has a helpful subsystem reality table showing OpenAI harness, Qdrant, persisted bandit, and eval reports. 

But later sections still say 151 tests, old coverage, old Docker/Kubernetes stubs, and cross-process resume as future work.  

Move the old content to `HISTORY.md` and make `FINAL_REPORT.md` current-only.

## 3. The committed multi-harness report does not show OpenAI/Claude

This is subtle but important.

`ALPHA4_CHECKLIST.md` says the live multi-harness bakeoff compared OpenAI and Claude and both solved.  The sprint report says the same. 

But the committed `multi_harness_trace_bakeoff.json` I inspected lists only `fake` and `patch` adapters, with zero solved cells.  

That does **not** invalidate the live claim, but it means the committed artifact does not prove it. For review, commit a redacted live report showing OpenAI and Claude rows, or add a separate `multi_harness_trace_bakeoff_live_redacted.json`.

## 4. Docker live evidence is optional/skipped in this environment

The committed pytest artifact shows 5 skipped tests, including Docker/pgvector unavailability.  Docker runner tests exist, but reviewers should still run a Docker-capable CI/lab gate before trusting production sandboxing.

The Docker runner test includes a real no-network check when Docker is available, but it is skipped without Docker. 

## 5. Claude/OpenAI harnesses are true ACP harnesses, but not vendor coding-agent SDK wrappers

This is not a criticism; it is a clarity point.

The branch now has two real **tool-loop harnesses** implemented in ACP, which is a major step. But these are still not Claude Code Agent SDK, Codex SDK, or OpenHands SDK adapters. The next stage should add at least one vendor/native coding-agent harness wrapper.

## 6. Harness tools still need deeper command-sandbox alignment

`harness_base.make_tools` currently uses a local `CommandRunner` bound to the workspace path.  The governance policy says true harnesses require Docker, but the shared harness tool implementation itself is local unless orchestration swaps in Docker elsewhere.

That may be okay if orchestration only creates Docker-backed workspaces/runners for harnesses. But this needs a direct test: true harness tool `run_command` must execute inside Docker when Docker backend is selected.

## 7. pgvector is still not real

Qdrant is real via `qdrant_client`; pgvector remains a transparent memory fallback until DSN/deps are configured. 

That is fine, but the roadmap should still include a real pgvector contract test.

---

# Constructive feedback

## 1. Open the PR after one doc/artifact cleanup commit

Before review, do one short cleanup commit:

```text
1. Update CURRENT_STATUS.md for Alpha 4.
2. Replace stale FINAL_REPORT.md body or move old parts to HISTORY.md.
3. Commit a redacted live OpenAI-vs-Claude bakeoff artifact.
4. Add a doc consistency test that compares CURRENT_STATUS, pytest.txt, coverage.txt, and ALPHA4_CHECKLIST.
```

Then open the PR.

## 2. Rename this milestone clearly

Call the branch state:

```text
Alpha 4 — multi-harness empirical router
```

The key achieved milestone is:

```text
two ACP true harnesses
normalized agent traces
no-patch bakeoff framework
router replay from bakeoff outcomes
calibrated evaluation loop
```

That is now real enough to review.

## 3. Separate “ACP harness” from “vendor harness”

Use precise adapter categories:

```text
deterministic baseline: fake, patch
simple model adapter: one-shot JSON edit
ACP true harness: OpenAIHarnessAdapter, ClaudeHarnessAdapter
vendor/native coding-agent harness: Codex SDK, Claude Agent SDK, OpenHands SDK
```

This will prevent confusion.

## 4. Make live artifacts reviewable without exposing secrets

The live OpenAI/Claude bakeoff is the most important achievement. Provide a redacted artifact:

```json
{
  "adapters": ["openai_harness", "claude_harness"],
  "task": "bugfix/no_patch",
  "success": true,
  "tool_calls": ...,
  "file_writes": ...,
  "diff_summary": ...,
  "tokens": ...,
  "cost_usd": ...,
  "latency_s": ...
}
```

No prompt text or secrets required.

## 5. Make Docker enforcement impossible to bypass accidentally

The governance policy is correct. Now ensure that every path to `adapter.execute()` checks it.

The invariant should be:

```text
if adapter.is_harness and workspace.backend != "docker" and not override:
    no model call happens
    no tool call happens
    audit/policy violation is persisted
```

## 6. Make the router learn from real traces, not just rewards

Rewards are useful but blunt. Add features from `AgentTrace`:

```text
tool_call_count
commands_run
file_write_count
diff_lines
test_commands_run
tokens
cost
latency
error class
human-review result
post-merge result
```

These should feed the routing feature extractor and supervised predictors.

---

# Tests to add beyond the current suite

## A. Documentation and artifact consistency

Add a test that checks:

```text
CURRENT_STATUS.md test count == reports/pytest.txt test count
CURRENT_STATUS.md coverage == reports/coverage.txt coverage
FINAL_REPORT.md has no stale “151 tests” line
FINAL_REPORT.md has no stale “cross-process resume is future work” line
ALPHA4_CHECKLIST.md acceptance matches code-adapter registry
```

This would catch the current mismatch.

## B. Live artifact presence test

If `ALPHA4_CHECKLIST.md` claims live OpenAI+Claude bakeoff, require one of:

```text
evals/reports/multi_harness_trace_bakeoff_live_redacted.json
reports/live_openai_claude.txt
```

Validate that it contains rows for `openai_harness` and `claude_harness`.

## C. Harness governance end-to-end

Test the actual workflow path:

```text
true harness + local backend + no override => blocked before model call
true harness + local backend + override => allowed + persisted AuditEvent
true harness + docker backend => allowed
simple model + local backend => allowed + model_adapter_local audit
fake/patch + local backend => allowed
```

## D. Harness command execution backend parity

For both OpenAI and Claude harnesses, mock tool calls that invoke `run_command` and assert:

```text
local backend uses local CommandRunner only when allowed
docker backend uses DockerCommandRunner
recorded CommandRunRecord.resource_usage.backend == "docker"
```

## E. AgentTrace invariant tests

For every adapter:

```text
fake
patch
simple_llm
openai_harness
claude_harness
```

assert:

```text
exactly one AgentTrace per AgentAttempt
AgentTrace survives service restart
AgentTrace appears in full_run_graph
trace.adapter_name matches attempt.agent_name
trace.is_harness matches adapter.is_harness
trace.changed_files matches DiffBundle changed_files
```

## F. No-patch bakeoff should fail if patch metadata is provided

For the “real no-patch” bakeoff:

```text
metadata["files"] is forbidden
metadata["patch"] is forbidden
```

If the bakeoff claims to compare agents, it must not hand one agent the answer.

## G. Live OpenAI/Claude bakeoff gate

Optional, key-gated:

```bash
pytest -m live_openai -q
pytest -m live_second_harness -q
pytest -m live_multi_harness -q
```

Assertions:

```text
both adapters make tool calls
both write files
both produce diffs
both run or skip verification explicitly
both emit AgentTrace
no raw key in artifacts
```

## H. Docker live security gate

In Docker-capable CI:

```text
non-root
no network
memory limit
pid limit
workspace-only mount
cleanup
secret non-leakage
local-vs-docker parity
```

## I. Qdrant persistence test

The current Qdrant `:memory:` path is good, but add a persistent-location test:

```text
create QdrantStore(location=tempdir)
upsert records
reopen QdrantStore(location=tempdir)
query same records
delete snapshot
query returns none
```

## J. pgvector live contract

Optional DSN-gated:

```text
backend == "pgvector"
create extension if allowed
upsert
query
snapshot filter
delete snapshot
reconnect
```

Do not allow fallback in this test.

## K. Calibrated evaluator threshold test

Use a known labeled dataset:

```text
good fix
bad fix
test deletion
skip added
hardcoded fix
post-merge revert
human reject
human approve
```

Assert:

```text
Brier score reported
correlation reported
threshold recommendation changes when labels change
human-review threshold is persisted
```

## L. Router replay from traces

Create an `EvalRun` with known outcomes:

```text
openai_harness: success, cost high
claude_harness: success, cost lower
fake: fail
patch: fail
```

Replay into policy and assert:

```text
policy scores change
preferred action changes
replay is idempotent
cost penalty affects winner
post-merge revert can reverse winner
```

## M. 12-hour soak profile

Run:

```bash
uv run python evals/scripts/run_soak.py \
  --iterations 5000 \
  --concurrency 16 \
  --task-mix bugfix,fail,human,security \
  --backend docker-if-available
```

Track:

```text
p50/p95/p99 latency
RSS growth
FD growth
SQLite/Postgres lock retries
orphan worktrees
artifact bytes
policy arm count
agent trace count
reward events
audit events
```

## N. Multi-repo benchmark

Run the same tasks across at least three fixture repos:

```text
python package
typescript/frontend app
mixed monorepo fixture
```

Assert context compiler, verification plan, and routing features behave differently by repo.

---

# Next-level plan for an LLM coding agent

This is intentionally much more ambitious than the previous plan. Scope it as a **multi-hour to multi-day Alpha 5 sprint**.

## Mission: Alpha 5 — production-grade empirical routing lab

Turn ACP from “two-harness alpha” into a **repeatable empirical routing lab** that can compare multiple real harnesses across tasks, learn from traces and outcomes, and produce trusted routing policies.

---

## Workstream 1 — Status/documentation hardening

### Tasks

1. Regenerate `CURRENT_STATUS.md` from committed reports.
2. Replace stale `FINAL_REPORT.md` body with current Alpha 4 reality.
3. Move historical sections to `HISTORY.md`.
4. Add a `docs/status_schema.md` defining status categories:

   ```text
   real local
   real service-backed
   ACP true harness
   vendor harness
   simple model adapter
   fallback
   stub
   ```
5. Add `tests/integration/test_docs_consistency.py`.

### Acceptance

```bash
uv run pytest tests/integration/test_docs_consistency.py -q
```

No stale 151/305 test counts; no stale “future work” claims for completed features.

---

## Workstream 2 — Live artifact discipline

### Tasks

1. Add `reports/live/` with redacted JSON schemas:

   ```text
   live_openai_harness.json
   live_claude_harness.json
   live_openai_claude_bakeoff.json
   ```
2. Add a script:

   ```bash
   uv run python evals/scripts/redact_live_report.py
   ```
3. Ensure secrets, raw prompts, full file contents, and provider response IDs are redacted.
4. Add schema tests for live reports.

### Acceptance

The PR contains a redacted live report showing both `openai_harness` and `claude_harness` solved the same no-patch task, with tool-call counts, changed files, tokens, cost, latency, and verification status.

---

## Workstream 3 — Harness backend enforcement

### Tasks

1. Wire `PolicyEngine.check_execution_backend` into the orchestration launch node.
2. Add a `WorkspaceBackendPolicy` object to `RoutingAction`.
3. Add config:

   ```text
   ACP_WORKSPACE_BACKEND=local|docker
   ACP_ALLOW_LOCAL_HARNESS=false
   ```
4. Persist audit events for:

   ```text
   harness_local_blocked
   local_harness_override
   model_adapter_local
   docker_required
   ```
5. Add tests proving no model call happens if governance blocks execution.

### Acceptance

A true harness cannot run locally unless an explicit override is set and persisted as an audit event.

---

## Workstream 4 — AgentTrace invariant everywhere

### Tasks

1. Make `AgentTrace` creation part of the attempt finalization path.
2. Synthesize traces for adapters that do not produce tool calls.
3. Persist trace rows in `_persist_run`.
4. Include `agent_traces` in `full_run_graph`.
5. Add trace diff consistency checks.

### Acceptance

Every `AgentAttempt` has exactly one `AgentTrace`; no exceptions.

---

## Workstream 5 — True no-patch multi-harness benchmark suite

### Tasks

Create `evals/datasets/no_patch_tasks.yaml` with at least 50 tasks:

```text
10 bugfix
10 test generation
10 small feature
10 refactor
5 security
5 migration
```

For each task:

```text
repo fixture
task body
acceptance criteria
gold files
verification commands
risk level
expected human-review status
```

Build fixtures:

```text
python_buggy_app
python_package_with_cli
typescript_react_app
mixed_monorepo
security_sensitive_app
migration_app
```

### Acceptance

No task may use `metadata["files"]` or `metadata["patch"]`.

---

## Workstream 6 — Multi-harness bakeoff engine v2

### Tasks

Implement:

```bash
acp eval multi-harness-bakeoff \
  --dataset evals/datasets/no_patch_tasks.yaml \
  --adapters openai_harness,claude_harness,patch,fake \
  --repetitions 3 \
  --backend docker \
  --out evals/reports/multi_harness_v2.json
```

Metrics:

```text
success
verification_pass
reward
human_review_required
tool_calls
commands
file_reads
file_writes
changed_files
diff_lines
tokens
cost
latency
adversarial_findings
post_merge_replay_result
```

### Acceptance

The report has per-task, per-adapter, per-run metrics and aggregates by adapter/task type/risk.

---

## Workstream 7 — Router learning from traces

### Tasks

Extend routing features with trace-derived history:

```text
agent_success_by_task_type
agent_cost_by_task_type
agent_latency_by_task_type
agent_human_review_rate
agent_post_merge_failure_rate
agent_trace_complexity_score
agent_context_efficiency
```

Implement `PolicyObservation`:

```text
eval_run_id
task_id
attempt_id
action_key
reward
propensity
trace_features
outcome_source
```

Replay:

```bash
acp policy replay-eval <eval-run-id>
```

### Acceptance

After replaying a multi-harness bakeoff, candidate scores change and the router’s preferred harness changes on at least one task class.

---

## Workstream 8 — Delayed outcome simulator and post-merge lab

### Tasks

Implement synthetic delayed outcomes:

```text
merged
reverted after N days
incident
issue reopened
review rounds
production latency regression
```

Add replay:

```bash
acp eval simulate-postmerge --eval-run <id>
```

Update rewards and policy observations.

### Acceptance

A previously preferred harness can be downgraded after delayed negative outcomes.

---

## Workstream 9 — Evaluator calibration v2

### Tasks

Create calibration dataset with human/post-merge truth:

```text
clean fix
bad fix
partial fix
test deletion
skip addition
hardcoded fix
security regression
large unrelated diff
post-merge revert
```

Report per evaluator:

```text
objective
weak supervision
LLM judge
adversarial detector
combined evaluator
```

Metrics:

```text
accuracy
precision/recall
Brier
ECE
correlation
recommended human-review threshold
false auto-approve risk
```

### Acceptance

Calibration report persists as `EvalRun(kind=calibration)` and outputs a recommended threshold.

---

## Workstream 10 — Docker/Kubernetes security lab

### Tasks

Add `evals/scripts/run_sandbox_redteam.py`:

Attacks:

```text
env exfiltration
network exfiltration
parent directory read
symlink escape
hardlink escape
fork bomb
memory bomb
massive stdout
attempt to mutate .git
attempt to disable tests
attempt to write outside workspace
```

Backends:

```text
local
docker
kubernetes stub/optional
```

### Acceptance

Local backend is explicitly marked unsafe for true harnesses; Docker backend passes all enforceable checks.

---

## Workstream 11 — Real service integrations

### Tasks

Implement real:

```text
pgvector with DSN
Qdrant persistent path + server URL
OpenTelemetry OTLP exporter
Braintrust/LangSmith export stubs with clear unavailable states
```

Add live markers:

```text
live_pgvector
live_qdrant
live_otlp
```

### Acceptance

No service-backed test silently falls back to memory.

---

## Workstream 12 — Cost and budget enforcement

### Tasks

Add budget ledger:

```text
BudgetLedger
BudgetEvent
BudgetPolicy
```

Track:

```text
estimated cost
actual token usage
cost per task
cost per eval
cost per repo
daily cap
per-run cap
per-agent cap
```

Hard-stop harness loop when:

```text
max cost exceeded
max wall time exceeded
max steps exceeded
max tool calls exceeded
```

### Acceptance

Budget violations produce structured failures and do not write unbounded traces.

---

## Workstream 13 — Context compiler v2

### Tasks

Add context strategy experiments:

```text
minimal
bug_reproduction
architecture
test_focused
recent_changes
prior_failures
full_file
symbol_graph
```

Add gold-file benchmark across all fixture repos.

Metrics:

```text
recall@k
MRR
token cost
latency
agent success impact
cost impact
```

### Acceptance

Routing can choose context strategy, not just agent.

---

## Workstream 14 — Human review studio backend

### Tasks

Add backend support for:

```text
review queue filters
uncertainty reason
trace summary
diff summary
evidence summary
weak-label summary
judge disagreement
one-click label
convert label to eval case
```

API:

```text
GET /reviews?priority=...
GET /reviews/{id}/bundle
POST /reviews/{id}/label
POST /reviews/{id}/make-eval-case
```

### Acceptance

Every human label becomes reusable training/eval data.

---

## Workstream 15 — Release gate and Alpha 5 report

### Tasks

Generate:

```text
ALPHA5_REPORT.md
ALPHA5_CHECKLIST.md
evals/reports/multi_harness_v2.json
evals/reports/router_replay.json
evals/reports/calibration_v2.json
evals/reports/sandbox_redteam.json
evals/reports/context_strategy_benchmark.json
```

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make security-redteam
make bandit-monte-carlo
make retriever-stress
make alpha4-artifacts
make alpha5-artifacts
```

Optional live:

```bash
make live-openai
make live-second-harness
make live-docker
make live-qdrant
```

### Acceptance

A reviewer can inspect the artifacts and answer:

```text
Which harness is best for each task type?
Why did the router choose it?
What context did it receive?
What did it cost?
How was it verified?
Did the evaluator agree with humans?
Did delayed outcomes change the ranking?
```

---

# Merge recommendation

Open the PR after one cleanup commit that updates `CURRENT_STATUS.md` and replaces/archive stale `FINAL_REPORT.md` sections. The technical branch is now strong enough for PR review, but stale docs will distract reviewers.

Merge only after:

```text
1. CI confirms 329-pass gate.
2. CURRENT_STATUS.md matches reports/pytest.txt and reports/coverage.txt.
3. A redacted live OpenAI-vs-Claude bakeoff artifact is committed.
4. Docker live evidence is either attached or explicitly skipped with reason.
5. The reviewer spot-checks full_run_graph and AgentTrace persistence.
```

The project has crossed an important threshold: it now has **two true ACP harnesses and normalized traces**, so the next stage should focus on empirical routing quality, delayed outcomes, calibration, and production-grade security gates.
