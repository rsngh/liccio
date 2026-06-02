# Current Status

> **This is a local v0 / alpha, not production-grade.** It is an end-to-end,
> no-key prototype of the agent-control-plane loop with a growing set of
> production primitives. External agent harnesses, container isolation, and
> managed retrieval/observability backends are optional and partially stubbed.

Last updated: 2026-06-01 (Alpha 5). Tests: 371 passing, 6 skipped
(docker/pgvector unavailable) — see `reports/pytest.txt`; `ruff` + `mypy` clean;
87% line coverage (unit+integration). Gate: `uv run pytest -q &&
uv run ruff check . && uv run mypy src`.

**Alpha 4 — multi-harness empirical router.** Two real tool-loop harnesses now
exist (`openai_harness`, `claude_harness`), the execution-backend policy is
enforced in orchestration, every attempt carries a normalized `AgentTrace`, a
multi-harness no-patch bakeoff compares adapters and persists as an `EvalRun`,
the router learns from those bakeoffs, and the evaluator ladder is calibrated
with a human-review threshold recommendation. See `ALPHA4_CHECKLIST.md`.

**Alpha 5 — production-grade empirical routing lab.** Dataset-driven bakeoff v2
(`acp eval multi-harness-bakeoff`) over a no-patch dataset across six task
types; routing learns from per (adapter, task_type) **trace features**; a
**delayed-outcome simulator** downgrades day-0 favourites that revert; **budget
ledger** hard-stops every harness loop (cost/wall/steps/tool_calls); **calibration
v2** scores every evaluator (accuracy/precision/recall/Brier/ECE + false-auto-
approve risk); a **sandbox red-team lab** marks the local backend unsafe for true
harnesses; and a **redacted live OpenAI-vs-Claude bakeoff** artifact is committed.
See `ALPHA5_CHECKLIST.md` / `ALPHA5_REPORT.md` and the status vocabulary in
`docs/status_schema.md`.

## Implemented (real, tested)

- **Core loop** task → context → route → attempt → verify → evaluate → (human) →
  reward → learn, as a durable 16-node `WorkflowRunner`.
- **Data model & persistence**: 24 entity tables + `EntityStore` (queryable
  columns + JSON payload), Alembic migrations (incl. `run_states`, `spans`).
- **Durable resume**: `WorkflowState` persisted; runs reload + rehydrate from DB
  and resume (incl. human-review) across a fresh process.
- **Full provenance**: every run persists task/snapshot/context-pack/plan/
  decision/attempts/diffs/verification-runs/evidence/evaluation/weak-label/
  reward/spans; reconstructable via `all_for_task`.
- **Adaptive routing in the live loop**: multi-agent candidates + constraints +
  `SimulatedBanditPolicy` (epsilon-greedy/Thompson) that learns across runs via
  `observe_reward`; full `RoutingDecision` (candidates/scores/propensity) logged.
- **Eval ladder integrated**: objective evaluator + 15 weak-supervision LFs + 5
  fake LLM judges + active-learning selector + adversarial detectors, folded into
  the human-review decision.
- **Mediated command execution**: timeout/process-group kill, `is_relative_to`
  cwd containment, secret-scrubbed child env, output truncation → artifacts.
- **Context compiler**: indexer + Tree-sitter (Python) / AST parsing + hybrid
  retrieval (BM25-or-overlap + hashing-embedding + boosts) + token budgeter +
  immutable hashable ContextPack; differentiated strategies.
- **Verification**: detectors + pytest/static/security/coverage runners +
  evidence aggregation + adversarial (anti-gaming) detectors.
- **Observability**: node-level spans persisted per trace; JSONL exporter; metrics.
- **Post-merge loop**: outcome ingestion matures reward down on revert/incident.
- **API + CLI**: repos/tasks/runs (+ trace/diff/evidence/evaluation/cancel),
  reviews (+ label/resolve), policies (train/promote/rollback); demos.
- **Long evals**: bandit Monte Carlo (beats random w/ CI), retriever stress,
  chaos/resume, security red-team, soak, bakeoff.

## Partial (started, not hardened)

- **Crash-resume** (D1B3 ✓): durable resume works; per-node fault-injection now
  covers *post-persist* stop, *post-persist* exception, **and pre-persist crash**
  (`fail_before_node`) across all 15 non-terminal nodes, asserting single-shot
  finalize/reward and per-node re-execution idempotency.
- **Bakeoff/soak reports**: present; being upgraded to richer machine-readable
  matrices + operational metrics (D2B4/D2B5).
- **Vector retrieval** (D2B3 ✓): config-driven selection
  (`acp.context.factory.make_embedder` / `make_vector_store`) picks the best
  available backend and degrades to hashing + in-memory; `ContextCompiler` now
  auto-selects and records the choice in the retrieval trace; `PgVectorStore`
  has real psycopg + pgvector SQL wiring (cosine `<=>`), buffering in memory
  without a DSN.
- **Coverage**: ~85% (target 85%); optional/stub paths pull the total down.

## Stubbed / optional (degrade gracefully)

- **True tool-loop harnesses**: `openai_harness` (OpenAI) and `claude_harness`
  (Anthropic) are real harnesses (`is_harness=True`) that drive a read/write/run
  tool loop with full trace capture; live-verified. The Claude/Codex/OpenHands
  *simple model adapters* (single JSON-edit prompt) remain for cheap routing.
  All report `unavailable` without SDK/key/binary. Docker is required for a true
  harness unless `allow_local_harness` overrides (audited).
- **Container isolation** (Docker v1, D1B5 ✓): `DockerWorkspaceManager` mounts a
  host git worktree into a throwaway container (network/memory/cpu/pids limits,
  non-root, configurable network) and now implements the full workspace contract
  — `capture_diff` / `dirty` / `final_head` run on the host worktree. Kubernetes
  backend remains stubbed; local runner is cwd-contained + secret-scrubbed but
  not an OS-level sandbox.
- **Managed services**: pgvector/Qdrant, Braintrust/LangSmith/Phoenix exporters,
  MABWiser/VW bandits.

## Known risks

- Local `CommandRunner` is not a hard sandbox — use the Docker backend before
  running untrusted real agents.
- Simple model adapters can be prompt-injected; treat their output as untrusted
  and rely on verification + adversarial detectors.
- Coverage of optional/stub paths is low by design.
