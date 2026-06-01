# Current Status

> **This is a local v0 / alpha, not production-grade.** It is an end-to-end,
> no-key prototype of the agent-control-plane loop with a growing set of
> production primitives. External agent harnesses, container isolation, and
> managed retrieval/observability backends are optional and partially stubbed.

Last updated: 2026-06-01. Tests: 222 passing; `ruff` + `mypy` clean; ~85% line
coverage (unit+integration). Gate: `uv run pytest -q && uv run ruff check . &&
uv run mypy src`.

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

- **Crash-resume**: durable resume works; per-node fault-injection harness is
  being expanded (D1B3).
- **Bakeoff/soak reports**: present; being upgraded to richer machine-readable
  matrices + operational metrics (D2B4/D2B5).
- **Vector retrieval**: hashing-embedding default; pluggable VectorStore +
  OpenAI/sentence-transformer embedders in progress (D2B3).
- **Coverage**: ~85% (target 85%); optional/stub paths pull the total down.

## Stubbed / optional (degrade gracefully)

- **Real agent harnesses**: Claude/OpenAI/Codex/OpenHands adapters are *simple
  model adapters* (single JSON-edit prompt), not full tool-loop harnesses. They
  report `unavailable` without SDK/key/binary.
- **Container isolation**: Docker/Kubernetes workspace backends (Docker v1 in
  progress, D1B5); local runner is cwd-contained + secret-scrubbed but not an
  OS-level sandbox.
- **Managed services**: pgvector/Qdrant, Braintrust/LangSmith/Phoenix exporters,
  MABWiser/VW bandits.

## Known risks

- Local `CommandRunner` is not a hard sandbox — use the Docker backend before
  running untrusted real agents.
- Simple model adapters can be prompt-injected; treat their output as untrusted
  and rely on verification + adversarial detectors.
- Coverage of optional/stub paths is low by design.
