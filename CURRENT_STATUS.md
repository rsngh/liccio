# Current Status

> **This is a local v0 / alpha, not production-grade.** It is an end-to-end,
> no-key prototype of the agent-control-plane loop with a growing set of
> production primitives. External agent harnesses, container isolation, and
> managed retrieval/observability backends are optional and partially stubbed.

Last updated: 2026-06-03 (Round 12 — measurement-trust). Tests: 1063 passing, 5 skipped (docker/pgvector/live-codex unavailable) — see `reports/pytest.txt`;
`ruff` + `mypy` clean across 258 source files; see `reports/coverage.txt`. Gate:
`uv run pytest -q && uv run ruff check . && uv run mypy src && uv run alembic
upgrade head && acp reports validate` (46 artifacts valid).

**Round 12 — measurement-trust layer.** ACP now classifies every attempt into an
`AttemptOutcome` (conclusive task signal vs infra/inconclusive noise) so infra
timeouts and provider errors never poison capability measurement; a durable
`attempt_outcomes` table persists the evidence. Provider calls run under a declared
`ProviderPolicy` (`max_retries=0` + per-call timeout). A `HarnessAvailabilityAudit`
makes a silently-absent harness loud, tool-activation metrics (`tools_required` /
`activation_failure_reason`) live on every `AgentTrace`, the capability matrix and
policy dossier carry conclusive-vs-infra columns, cost is a first-class tiebreaker
across matrix/Pareto/OPE/regret, and `acp health --mode production` gates on harness
availability + measurement non-contamination. A measurement mutation suite is the
self-check. See `ROUND12_REPORT.md` and `acp measurement hygiene`.

**Round 13 — preproduction router.** `AttemptOutcome` is now the mandatory learning gate (`evaluation/learning_gate.py`): only conclusive attempts update solve-rate/OPE quality. A measurement-quality score (8 dimensions) gates production health (`measurement_quality_trusted`); the capability matrix (v3), cost-aware OPE (v3, 5 objective profiles), and policy dossier all carry measurement-quality; classified outcomes persist to a queryable `attempt_outcomes` table; the live corpus spans 6 task types; relative trajectory judgments feed preference learning. See `ALPHA13_REPORT.md`.

**Alpha 4 — multi-harness empirical router.** Two real tool-loop harnesses now
exist (`openai_harness`, `claude_harness`), the execution-backend policy is
enforced in orchestration, every attempt carries a normalized `AgentTrace`, a
multi-harness no-patch bakeoff compares adapters and persists as an `EvalRun`,
the router learns from those bakeoffs, and the evaluator ladder is calibrated
with a human-review threshold recommendation. See `ALPHA4_CHECKLIST.md`.

**Alpha 12 — harness quality + workflow-shape learning.** **Harness metrics**
(`evaluation/harness_metrics.py`: HAR/HFR/PWL activation/adherence/pass-when-loaded
by model/harness/task-type; live result HAR=HFR=PWL=1.0 on real harness traces); a
governed **harness-evolution pipeline** (proposal->scan->eval->review->canary->
rollback; no promotion without eval+audit+rollback); **topology action learning**
(`RoutingAction.topology` + `TOPOLOGY_ACTIONS`: skip planner/reviewer, light/strict
verifier, branch_parallel, terminate, abstain — OPE-learnable, backward-compatible
arm keys); and a **relative trajectory judge** (8 axes + cross-judge audit + reward
sensitivity, feeding preference learning). See `ALPHA12_*`.

**Alpha 11 — production-readiness candidate.** Routing objectives are configurable
per task class (`core/pareto_config.py`; docs→cost_saver, security_fix→risk_min,
incident→success_max, high-risk safety override). Every run carries a **policy
decision dossier** (`acp policy dossier`: why this agent/context/cost/risk + why-not
others). **Health is mode-gated** (`acp health --mode production` exits nonzero
unless docker-live-security + OPE-overlap + fresh-test + manifest gates hold).
**Drift auto-demotion is durable** (persisted drift report + demotion event +
review item + promotion state). **Preference reward is governed** (advisory until
pairwise-accuracy / reviewer-agreement / post-merge / high-risk gates pass), a
**data-governance red-team** blocks all 6 attacks with zero leaks, a **production
policy pack** declares lab/staging/production requirements, and a productionized
**scheduler** (dependency graph + single-writer lock) runs the learning jobs. 34
artifacts manifest-validated. See `ALPHA11_*`.

**Alpha 9/10 — multi-objective decision system + scale hardening.** Routing is now
multi-objective: a **Pareto routing policy** (`routing/pareto_policy.py`) with 6
weight profiles (cost_saver…success_max) chooses on the (success/cost/latency/risk)
frontier. **Drift detection** auto-demotes a learned model when its predictions stop
matching outcomes; **preference learning** fits a pairwise reward from human labels;
**counterfactual** analysis reports per-decision regret; an **active-learning
executor** + **continuous-learning scheduler** close the loop; and `acp health`
returns a unified control-plane snapshot (status/degraded + artifact freshness).
Alpha 10 adds a **large empirical corpus** (930 sufficient capability cells, 1,740
preference pairs), a **v2 scale benchmark** (sub-quadratic), an **expanded
security/prompt-injection suite** (10 attack classes, zero leak), and **model/data
governance**. 24 committed artifacts are manifest-validated (`acp reports validate`).
See `ALPHA9_*`/`ALPHA10_*`.

**Alpha 8 — learned governance from exhaust.** ACP now learns from its own runs:
a **learned + ensemble viability assessor** (`core/viability_learned.py`) that
stays advisory until it makes zero high-risk false negatives on holdout; a
**context-strategy learner**; an **evaluator trust model** that cuts low-risk
human-review burden ~33% with no extra false auto-approves; a 9-class
**repair-strategy classifier**; completed training-dataset builders for
viability/context_strategy/trace_summary/verification_plan; a **fine-tuning
governance** gate (`training/model_governance.py`: beats rules+prompt baselines,
temporal+repo holdout, leakage+memorization audits, rollback plan) with a
**MemorizationAudit**; a **policy canary simulator** with guardrail rollback; an
**exploration designer** for coverage gaps; and **artifact-truth infrastructure**
(`acp reports validate`) that fails CI on any missing/malformed cited report. See
`ALPHA8_CHECKLIST.md` / `ALPHA8_REPORT.md`.

**Alpha 7 — policy-governed routing + training pipeline.** Every run produces a
`ViabilityAssessment` (cheap-vs-harness, abstain on unverifiable/ambiguous;
persisted + consumed by routing). An **OPE promotion gate** (`routing/promotion.py`,
`acp policy promotion-check`) turns an OPE report into a deploy/block decision —
statistical-trust (ESS/overlap/max-weight/DR-CI/SNIPS) + operational-safety
(cost/human-review/high-risk/calibration) conditions + a staged canary plan;
`acp policy real-log-ope` compares policies on real logs and refuses to rank when
overlap/ESS is poor. A **CapabilityMatrix** (`acp viability matrix`) flags
low-sample cells. A **training-data factory** (`acp dataset build`,
`acp train candidate-report`) distills redacted, leakage-audited datasets from run
exhaust and recommends fine-tuning only when justified. The **context-strategy
downstream benchmark** scores strategies by task success, the **codex_cli** vendor
harness is a real mediated loop, and the **review studio** converts labels into
training examples. See `ALPHA7_CHECKLIST.md` / `ALPHA7_REPORT.md`.

**Alpha 6 — self-improving multi-harness routing lab.** Offline policy
evaluation (`routing/ope.py`: IPS/SNIPS/clipped-IPS/**doubly-robust** + bootstrap
CIs + ESS/overlap diagnostics) estimates a target policy's value from logged
decisions without re-running agents (`acp policy evaluate-offline`); a
**supervised meta-router** (`SupervisedRoutingPolicy`) learns from `(context,
action)` features and, under OPE, beats random and ties the bandit; **joint
(agent × context-strategy) routing** recompiles context with the routed strategy;
a **vendor harness** category (`VendorHarnessAdapter` + `CapabilityRegistry`,
`claude_agent_sdk`/`codex_cli` shims) sits beside the ACP harnesses
(`openai_harness`, `claude_harness`); a **context-strategy benchmark** ranks
strategies per repo; a **human-review studio** backend turns labels into eval
cases; an **OTLP exporter** ships spans via OpenTelemetry; and a committed
**redacted live OpenAI experiment** shows a real no-patch solve. See
`ALPHA6_CHECKLIST.md` / `ALPHA6_REPORT.md`.

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
