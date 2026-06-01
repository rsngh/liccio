## Executive verdict

I inspected the current `feat/agent-control-plane` branch, including the Round‑3 files now fast-forwarded into it. I did **not** run the repo locally, so I’m treating the committed reports and tests as evidence, not as independent execution.

This is now a **credible Alpha 3 control-plane prototype**. It has moved meaningfully beyond “local v0”: it now includes full provenance, persisted run state, exhaustive crash-resume tests, Docker command execution, eval-report entities, persisted policy state, an OpenAI tool-loop harness, normalized agent traces, Qdrant-backed vector storage, evaluator calibration, post-merge reward replay, and committed merge-gate artifacts.

The highest-level caveat: the docs are still internally inconsistent. `CURRENT_STATUS.md` still says real agent harnesses are stubbed/simple adapters, while `FINAL_REPORT.md` and the code show `OpenAIHarnessAdapter` as a true harness.   That should be fixed before the PR is opened or reviewed.

---

# What has been implemented

## 1. Test/coverage gate and alpha posture

The committed pytest report supports the sprint claim: **305 passed, 4 skipped**, with two Docker skips due to Docker unavailable.  The committed coverage report shows **85%** total coverage. 

The branch also correctly positions the project as a **local v0 / alpha, not production-grade**. 

## 2. Durable control-plane loop and provenance

`CURRENT_STATUS.md` says the core task → context → route → attempt → verify → evaluate → human → reward → learn loop is implemented as a durable `WorkflowRunner`, with full provenance persisted for task, snapshot, context pack, plan, decision, attempts, diffs, verification runs, evidence, evaluation, weak label, reward, and spans. 

The DB model confirms this direction: it now includes `run_states`, `spans`, `policy_states`, `agent_traces`, and eval-report tables in addition to the earlier task/context/routing/attempt/evidence/reward entities.  

The service layer persists command runs, verification runs, evidence, weak labels, rewards, spans, and agent traces as part of `_persist_run`, and it restores learned bandit arms from `PolicyState` on service startup. 

## 3. Exhaustive crash-resume

This is a major improvement. The branch now has an exhaustive crash-resume test over every node except terminal finalization. It tests both “stop after node and resume” and “exception after node and resume,” and asserts exactly one finalization/reward.  

It also tests that a human-review pause does not finalize without a label, and that human labeling after restart finalizes exactly once. 

## 4. Merge-gate invariants

The repo now has an independent merge-gate test that checks no production-grade overclaim, verifies a full run graph after restart, and runs migrations cleanly.   

The PR checklist also lists the intended Alpha 2/3 gates: CI, full graph, exhaustive crash-resume, security red-team, Docker tests/skips, vector DB live tests, eval-report persistence, true harness adapter, persistent policy, and concurrent soak. 

## 5. OpenAI tool-loop harness

The original “no true harness” gap is partly closed. `OpenAIHarnessAdapter` is a real ACP-managed tool-loop harness: the model uses `read_file`, `write_file`, `run_command`, and `finish`, and the adapter captures tool calls, file writes, command records, diffs, tokens, cost, wall time, and budget/timeout behavior. 

The `HarnessTools` implementation enforces workspace-local path safety for read/write operations. 

There is also a live test, skipped unless `OPENAI_API_KEY` is present, that runs a real bugfix and asserts tool calls, file writes, diff capture, token capture, a session ID, and no secret leakage in tool summaries.  

Important nuance: this is a real **ACP harness** around OpenAI chat/tool calls. It is not the same as wrapping the OpenAI Codex SDK, Claude Agent SDK, or OpenHands SDK.

## 6. Normalized agent traces

`AgentTrace` is now a first-class schema, designed to normalize both true harness traces and simple JSON-edit model adapters into comparable traces. It tracks harness status, adapter name, model, session ID, tool-call count, file reads/writes, commands, changed files, diff lines, tokens, cost, wall time, and errors. 

The DB model also has an `agent_traces` table. 

This is exactly the right primitive for cross-agent routing.

## 7. Docker command execution

`DockerCommandRunner` is now implemented. It exposes the same surface as `CommandRunner`, but wraps commands in `docker run`, with the host Docker invocation still going through the mediated runner for timeouts, output capture, and redaction. 

The Docker runner rewrites the recorded command back to the logical in-container command and records backend metadata. 

There are tests for Docker argv wrapping and optional live Docker tests for `pwd` and no-network behavior.  

## 8. Governance for true harnesses

The governance layer now has execution-backend policy: fake/patch can run local, simple model adapters prefer Docker, and true harnesses require Docker unless an explicit local-harness override is granted and audited. 

The policy enforcement raises if a true harness runs outside Docker without override, and records an audit event when override is used. 

This is the correct default posture.

## 9. Vector store and retrieval

The vector-store layer now has a real `VectorStore` protocol, in-memory store, pgvector fallback flag, and real Qdrant client implementation. 

Qdrant is implemented using `qdrant_client`, supports collection creation, upsert, query with snapshot filter, and delete-by-snapshot. 

pgvector remains a fallback until a DSN and dependencies are configured. 

## 10. Evaluator calibration

There is now a calibration module that compares automated evaluator probabilities against human or post-merge ground truth, reporting accuracy, Brier score, correlation, and per-source accuracy.  

That is the right next step for moving from synthetic evals to calibrated automation.

---

# What has not been implemented or remains incomplete

## 1. `CURRENT_STATUS.md` is stale

This is the biggest documentation bug. It still says real agent harnesses are simple JSON-edit adapters and Docker is “in progress,” while `FINAL_REPORT.md`, the code, and tests now show `OpenAIHarnessAdapter`, `DockerCommandRunner`, `AgentTrace`, and richer eval/reporting work.  

Because `FINAL_REPORT.md` says `CURRENT_STATUS.md` is the source of truth, this mismatch is damaging. 

## 2. Only one true harness exists

The OpenAI harness closes the “no true harness” gap, but only for one provider. Claude, Codex, OpenHands, and SimpleLLM are still listed as simple model adapters. 

The original product thesis depends on routing across multiple real coding-agent harnesses. That still requires true Claude Agent SDK, Codex SDK, and OpenHands SDK adapters.

## 3. Docker is implemented, but live Docker coverage is skipped in the committed pytest report

The committed pytest report shows Docker tests skipped because Docker was unavailable. 

The code and tests are present, but a merge reviewer still needs a CI/lab environment with Docker available to verify in-container execution, no-network behavior, pid/memory limits, cleanup, and local-vs-Docker parity.

## 4. OpenAI harness live test is optional

The live OpenAI harness test is well-designed, but it is skipped unless `OPENAI_API_KEY` exists. 

That is correct for default CI, but the PR should include a committed live-run artifact or separate live CI job if the branch is claiming “live verified.”

## 5. pgvector is not implemented as a real backend

The pgvector class exposes a visible `memory-fallback` backend and still forwards operations to an in-memory store unless DSN/dependencies exist. 

That is honest and fine, but it remains incomplete.

## 6. Some older `FINAL_REPORT.md` sections are intentionally stale, but still confusing

The top table is useful, but the older body still says 151 tests, old coverage, old optional-stub wording, and older “cross-process resume is follow-up” language.  

Even if the file says it is historical, reviewers will still read it. Either move old content to `HISTORY.md` or regenerate it.

## 7. Production observability is still not complete

The branch has in-process spans and JSONL, but Braintrust/LangSmith/Phoenix and full OpenTelemetry exporter wiring still appear optional. The subsystem table marks OTel optional. 

## 8. Human evaluator calibration exists, but needs real data

The calibration module is correct structurally, but calibration quality depends on enough human/post-merge labels. Right now, this is a framework plus tests, not yet a proven calibrated evaluator.

---

# Constructive feedback

## Open the PR now, but fix docs first

I would open the PR from `feat/agent-control-plane`, but before asking for review, do a doc cleanup commit:

1. Update `CURRENT_STATUS.md` to include Round 3 reality: `OpenAIHarnessAdapter`, `AgentTrace`, DockerCommandRunner, persisted eval entities, persisted bandit, Qdrant, evaluator calibration.
2. Move stale `FINAL_REPORT.md` historical sections to `HISTORY.md`, or regenerate the whole file.
3. Make one place authoritative for:

   ```text
   test count
   coverage
   skipped tests
   live tests run
   real vs fallback components
   known risks
   ```

## Don’t claim “multi-agent harness routing” yet

You now have one true harness plus several simple adapters. That is a major step, but the product thesis requires routing between **multiple real harnesses**. Phrase it as:

> “The platform now supports true harness traces and has one live OpenAI harness; Claude/Codex/OpenHands true harness adapters are next.”

## Make Docker mandatory in the real-agent path

The governance policy is correct. Now enforce it in every path that can launch `OpenAIHarnessAdapter` or future harnesses. The policy should be impossible to bypass accidentally. The override should require:

```text
explicit flag
audit event
reason
actor
trace_id
```

## Upgrade the bakeoff from “can solve” to “can compare”

The current platform can run and trace. The next moat is comparative learning:

```text
same task
same repo
same context budget
same verification policy
OpenAIHarness vs ClaudeAgentSDK vs CodexSDK vs OpenHands
normalized AgentTrace
reward and post-merge outcome
policy update
```

## Treat live tests as separate quality gates

Default CI should remain keyless. But add a nightly or manually triggered live workflow:

```text
live-openai
live-docker
live-qdrant
live-codex-when-available
live-claude-when-available
```

Keep those results as artifacts.

---

# Additional tests to run

## 1. Documentation consistency test

Add a test that parses `CURRENT_STATUS.md`, `FINAL_REPORT.md`, `reports/pytest.txt`, and `reports/coverage.txt` and asserts:

```text
test count matches
coverage matches
known skipped tests match
source-of-truth statement is accurate
no stale “future work” line contradicts implemented subsystem table
```

## 2. Harness governance integration test

Test the actual orchestration path, not just `PolicyEngine`:

```text
OpenAIHarnessAdapter + local backend + no override => fail before execution
OpenAIHarnessAdapter + local backend + override => run and audit local_harness_override
OpenAIHarnessAdapter + Docker backend => run without override
Simple model adapter + local backend => audit model_adapter_local
Fake/patch + local backend => allowed
```

## 3. AgentTrace completeness test

For every adapter type:

```text
fake
patch
simple model
OpenAIHarness
```

assert a persisted `AgentTrace` exists and includes:

```text
adapter_name
is_harness
status
changed_files
tool_calls
file_writes
commands
tokens/cost where applicable
attempt_id
task_id
```

## 4. Multi-harness bakeoff once another harness exists

As soon as Claude/Codex/OpenHands harness lands:

```text
same task
same repo
same seed
same context pack
same budget
same Docker backend
compare AgentTrace + RewardEvent
```

## 5. Live Docker security gate

Run in a Docker-capable CI/lab:

```text
no network
non-root
memory limit
pid limit
workspace mount only
diff capture
cleanup
secret non-leakage
```

The current committed pytest run skipped Docker due to no daemon. 

## 6. Live OpenAI harness artifact

Run `tests/live/test_openai_harness.py` with `OPENAI_API_KEY`, capture:

```text
pytest output
AgentTrace JSON
diff
tool-call summaries
cost/tokens
no-secret scan
```

The test exists and checks those core properties, but it is optional by default. 

## 7. pgvector live contract

Add a live pgvector test that refuses to fall back:

```text
backend == "pgvector"
upsert
query
snapshot filter
delete snapshot
restart connection
query persists
```

## 8. Qdrant persistence test

The Qdrant `:memory:` engine is good for local tests, but add a file-path or service-backed persistence test:

```text
create store at temp path
upsert
close/reopen client
query still returns records
delete snapshot
query returns none
```

## 9. Evaluator calibration with adversarial labels

Create a calibration set with:

```text
good fix
bad fix
test-deleting fix
skip-test fix
hardcoded fix
large unrelated diff
security-sensitive diff
post-merge revert
```

Assert Brier score and per-source accuracy are reported and persisted.

## 10. Long concurrent soak with live Docker optional

Run:

```bash
uv run python evals/scripts/run_soak.py \
  --iterations 1000 \
  --concurrency 16 \
  --task-mix bugfix,fail,human
```

Record:

```text
RSS growth
FD growth
DB lock retries
orphan worktrees
artifact bytes
p95/p99 latency
policy arm drift
failure taxonomy
```

---

# Next two-day plan for an LLM coding agent

## Mission

Take ACP from **Alpha 3** to **Alpha 4: multi-harness empirical router**.

The goal is to make the product’s central promise real:

> Same task, same repo, same context, multiple real harnesses, normalized traces, objective verification, calibrated evaluation, and learned routing.

---

## Day 1 — Clean merge state and harden current alpha

### Block A — Documentation and report reconciliation

1. Regenerate:

   ```text
   CURRENT_STATUS.md
   FINAL_REPORT.md
   PR_CHECKLIST.md
   ```
2. Make `CURRENT_STATUS.md` reflect Round 3:

   ```text
   OpenAIHarnessAdapter true harness
   AgentTrace persisted
   DockerCommandRunner implemented
   Qdrant real local/service engine
   pgvector explicit fallback
   EvalRun/EvalReport entities
   persisted bandit state
   evaluator calibration
   post-merge replay
   ```
3. Move stale historical sections from `FINAL_REPORT.md` to `HISTORY.md`.

Acceptance:

```bash
uv run pytest tests/integration/test_merge_gate.py -q
```

and no doc contradictions.

---

### Block B — Harness governance enforcement in orchestration

Wire `PolicyEngine.check_execution_backend` directly into the agent-launch path.

Required behavior:

```text
true harness + local backend => blocked
true harness + Docker backend => allowed
true harness + local override => allowed + AuditEvent
simple model + local => allowed + warning audit
fake/patch + local => allowed
```

Tests:

```text
test_true_harness_local_blocked_in_workflow
test_true_harness_local_override_audited
test_true_harness_docker_allowed
test_simple_model_local_audited
test_fake_patch_local_allowed
```

---

### Block C — AgentTrace as mandatory invariant

Make `AgentTrace` required for every `AgentAttempt`.

If an adapter returns no trace metadata, synthesize a minimal trace.

Tests:

```text
test_every_attempt_has_agent_trace
test_patch_agent_trace
test_fake_agent_trace
test_simple_model_trace
test_openai_harness_trace
test_run_graph_includes_agent_traces_after_restart
```

Acceptance:

```text
full_run_graph(run_id)["agent_traces"] is non-empty for every attempt.
```

---

### Block D — Live Docker evidence pack

Add a Docker live report script:

```bash
uv run python evals/scripts/run_docker_security_check.py
```

It should produce:

```text
evals/reports/docker_security.json
evals/reports/docker_security.md
```

Checks:

```text
pwd=/workspace
id -u != 0
network none blocks urllib/curl
memory hog fails
pid limit works
workspace file write reflected on host
cleanup removes worktree
```

Skip gracefully if Docker unavailable, but make the skip explicit.

---

## Day 2 — Add second real harness and empirical routing

### Block E — Implement Claude Agent SDK or OpenHands true harness

Pick one real harness. I would choose **OpenHands** if workspace/tool traces are easier to capture, or **Claude Agent SDK** if available in the environment.

Adapter contract:

```text
is_harness=True
Docker required by default
captures session_id
captures tool calls
captures file reads/writes
captures command runs
captures diff
captures tokens/cost if available
respects max_steps
respects max_wall_time
respects max_cost
never receives secrets by default
```

Tests:

```text
test_adapter_health_unavailable_cleanly
test_adapter_trace_schema_offline
test_adapter_live_tiny_bugfix_if_configured
test_adapter_docker_required
test_adapter_no_secret_leak
```

Acceptance:

```text
At least two true harness classes exist: OpenAIHarnessAdapter + one external coding-agent harness.
```

---

### Block F — Multi-harness no-patch bakeoff

Create a no-pre-supplied-patch benchmark:

```text
bugfix task
test-generation task
small feature task
refactor task
security-sensitive task
```

No `metadata["files"]` allowed.

Run matrix:

```text
OpenAIHarnessAdapter
SecondHarnessAdapter
SimpleLLM adapter
Patch baseline where applicable
Fake baseline
```

Metrics:

```text
success
verification pass
reward
tool calls
commands
file writes
tokens
cost
latency
human review required
adversarial findings
```

Persist as `EvalRun`.

Tests:

```text
test_no_patch_bakeoff_rejects_metadata_files
test_multi_harness_bakeoff_persists_agent_traces
test_bakeoff_compares_trace_metrics
test_bakeoff_failure_taxonomy
```

---

### Block G — Router learns from harness bakeoff

Feed `EvalRun` results into policy state.

Implement:

```text
PolicyObservation from EvalAttempt
observe_reward for each evaluated action
policy replay from EvalRun
policy report showing action preference changes
```

Tests:

```text
test_policy_learns_from_eval_run
test_policy_prefers_successful_harness_after_replay
test_policy_penalizes_high_cost_equal_quality_agent
test_policy_replay_idempotent
```

Acceptance:

```text
Running the same task after replay changes candidate scores or selected action.
```

---

### Block H — Calibrated evaluator loop

Use human labels and post-merge replay to calibrate the evaluation ladder.

Implement:

```text
CalibrationRun entity or EvalRun kind=calibration
calibration report persisted
per-signal Brier/accuracy/correlation
threshold recommendation for human-review gating
```

Tests:

```text
test_calibration_report_persisted
test_bad_weak_signal_gets_low_score
test_post_merge_revert_reduces_calibration_truth
test_human_label_overrides_objective_success
```

---

### Block I — PR/merge gate for Alpha 4

Add `ALPHA4_CHECKLIST.md`.

Required artifacts:

```text
reports/pytest.txt
reports/coverage.txt
evals/reports/docker_security.json
evals/reports/no_patch_bakeoff.json
evals/reports/multi_harness_trace_bakeoff.json
evals/reports/calibration.json
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
```

Optional live gates:

```bash
pytest -m live_openai
pytest -m live_docker
pytest -m live_second_harness
```

---

# Merge recommendation

Open the PR now, but before merge I would require one cleanup commit:

```text
1. Update CURRENT_STATUS.md to include Round 3 reality.
2. Remove or archive stale FINAL_REPORT.md sections.
3. Add/confirm doc-consistency test.
4. Attach committed pytest/coverage/live-run reports.
```

Then merge if the PR CI is green.

The project is now past “prototype plumbing” and into the genuinely interesting part: **empirical routing between real harnesses using normalized traces and calibrated outcomes**. The next two days should focus almost entirely on adding a second true harness, proving Docker-enforced execution, and making the router learn from real multi-harness bakeoffs.
