# Round 6 — Alpha 6: the self-improving multi-harness routing lab

> Round 5 (Alpha 5, archived in `GOALS5.md`) delivered the empirical routing
> *lab*: a no-patch dataset, a dataset-driven multi-harness bakeoff v2, router
> learning from trace features, a delayed-outcome simulator, per-evaluator
> calibration v2, a sandbox red-team lab, a budget ledger with hard-stops, and
> docs/artifact discipline. Alpha 5 can *measure* harnesses. Alpha 6 makes the
> control plane **learn to route correctly and prove it counterfactually**, adds
> **vendor/native coding-agent harnesses**, routes **context strategy as a first-
> class decision**, and finishes the **real service + observability** backends.

## Mission

Turn ACP from "a lab that measures harnesses" into a **self-improving routing
control plane**: it logs propensity-scored decisions, evaluates *new* policies
offline against that log (no re-running agents), trains a supervised meta-router
from trace features and outcomes, jointly routes `(agent × context-strategy)`,
and benchmarks across multiple real repositories — with vendor coding-agent
harnesses and production-grade observability behind it.

A reviewer should be able to answer, from committed artifacts:

```
For each task type & repo, which (harness, context-strategy) is best, and why?
If we deploy the new (supervised) policy, what is its expected reward/cost vs the
  logged policy — estimated offline, with confidence intervals?
Does the bandit, the supervised meta-router, or a static policy win on the log?
Which context strategy maximizes retrieval recall@k per repo, at what token cost?
Did delayed (post-merge) outcomes change any of the above?
```

---

## Foundation already landed this round (Alpha-6 down payment)

These shipped first and the rest of Alpha 6 builds on them:

- **D1B5 — Docker workspace backend v1**: `DockerWorkspaceManager` now implements
  the full workspace contract (`capture_diff`/`dirty`/`final_head` over the host
  worktree mounted into the container) with a configurable container network.
- **D2B3 — Pluggable vector retrieval**: `acp.context.factory` selects the best
  available embedder (OpenAI→sentence-transformers→hashing) and vector store
  (pgvector→qdrant→in-memory) with graceful degradation; `ContextCompiler`
  auto-selects and records the choice in the retrieval trace; `PgVectorStore`
  has real psycopg + pgvector SQL.
- **D1B3 — Per-node fault injection**: `fail_before_node` (pre-persist crash)
  + exhaustive resume/idempotency tests across all 15 non-terminal nodes.

---

## Workstream 1 — Vendor / native coding-agent harnesses

Alpha 5's harnesses are *ACP* tool-loops. Alpha 6 adds the **vendor harness**
category (status vocabulary: `vendor harness`) so the lab can compare ACP-managed
loops against native coding agents on equal footing.

### Tasks
1. `agents/vendor_base.py`: a `VendorHarnessAdapter` base that normalizes an
   external coding-agent process/SDK into the same `AgentTrace` surface.
2. `agents/claude_agent_sdk.py` and `agents/codex_cli.py`: capability-gated shims
   that report `unavailable` without the SDK/binary/key, and run a real loop when
   present. Register them with a `capability` (sdk/cli/api) in the registry.
3. A `CapabilityRegistry` describing each adapter's category, requirements, and
   live-availability so routing can exclude unavailable adapters.

### Acceptance
`acp agents list --capabilities` shows category + availability for every adapter;
vendor adapters degrade cleanly; an available vendor adapter emits a valid
`AgentTrace` with `is_harness=True` and `category="vendor"`.

---

## Workstream 2 — Joint (agent × context-strategy) routing

### Tasks
1. Extend `RoutingAction`/`RoutingCandidate` with a `context_strategy` field so an
   action is `(agent, context_strategy)`.
2. The bandit policy operates over the joint action space; propensities are logged
   per joint action.
3. The runner compiles context using the routed strategy (not a fixed one).

### Acceptance
A run's `RoutingDecision` records the chosen context strategy; replaying a bakeoff
can flip the preferred *strategy* for a task class, independent of the agent.

---

## Workstream 3 — Offline policy evaluation (OPE) — the core new capability

Given a log of propensity-scored decisions + observed rewards, estimate the value
of a *different* policy without re-running agents.

### Tasks
1. `routing/ope.py` implementing IPS, self-normalized IPS (SNIPS), and a
   doubly-robust (DR) estimator with a fitted reward model, plus bootstrap CIs.
2. `acp policy evaluate-offline --eval-run <id> --policy <bandit|supervised|static>`
   producing `evals/reports/ope.json`.
3. A diagnostics layer: effective sample size, propensity overlap, clipping.

### Acceptance
On a synthetic log where a known policy is better, OPE ranks it above the logging
policy with non-overlapping bootstrap CIs; SNIPS/DR agree on the winner; estimates
are reproducible.

---

## Workstream 4 — Supervised meta-router

### Tasks
1. `routing/supervised.py`: train a calibrated predictor (logistic / gradient,
   pure-Python fallback) of `P(success)` and expected cost/latency from trace +
   task + repo features.
2. Expose it as a `RoutingPolicy` so it plugs into the runner.
3. Compare bandit vs supervised vs static via OPE (WS3) on the same log.

### Acceptance
The supervised policy beats random and at least ties the bandit under OPE on the
benchmark log; predictions are calibrated (reliability curve reported).

---

## Workstream 5 — Multi-repo benchmark + context-strategy gold-file benchmark

### Tasks
1. Ensure ≥3 distinct fixture repos (python package, TS/react app, mixed monorepo)
   with gold files and verification commands.
2. `evals/context_strategy_benchmark.py`: per strategy × repo, compute recall@k,
   MRR, token cost, latency against gold files. CLI + `evals/reports/`.
3. Cross-repo benchmark asserting context/verification/routing differ by repo.

### Acceptance
Report shows a different best context strategy for at least two repos; routing can
select strategy by repo.

---

## Workstream 6 — Human-review studio backend + API

### Tasks
1. Endpoints: `GET /reviews?priority=`, `GET /reviews/{id}/bundle` (trace + diff +
   evidence + weak-label + judge-disagreement summary), `POST /reviews/{id}/label`,
   `POST /reviews/{id}/make-eval-case`.
2. Label→eval-case conversion writes a reusable dataset row.

### Acceptance
Every human label can become an eval/training case; bundle endpoint returns a
complete, secret-free review package.

---

## Workstream 7 — Real services + observability finish

### Tasks
1. Real OTLP span exporter (`observability/otlp.py`) gated on `opentelemetry`;
   `live_otlp` marker test.
2. Qdrant persistent-path contract test (create→upsert→reopen→query→delete).
3. pgvector live contract test (DSN-gated, no fallback) exercising the real SQL.

### Acceptance
No service-backed test silently falls back to memory; OTLP export verified against
an in-memory span collector.

---

## Workstream 8 — Live OpenAI experiment lab (uses `OPENAI_API_KEY`)

### Tasks
1. A key-gated experiment that has `openai_harness` solve a real no-patch bugfix in
   a fixture repo, capturing a full `AgentTrace`.
2. Redact + commit `reports/live/alpha6_openai_experiment.json` (no secrets, no raw
   prompts, no full file contents).
3. Live OpenAI embedder experiment feeding the context-strategy benchmark.

### Acceptance
Committed redacted artifact shows tool calls, file writes, diff summary, tokens,
cost, latency, and verification status for a real OpenAI run.

---

## Workstream 9 — Alpha 6 report, gate, and checklist

### Tasks
1. `ALPHA6_CHECKLIST.md`, `ALPHA6_REPORT.md`, `make alpha6-artifacts`.
2. Regenerate `CURRENT_STATUS.md`; keep `docs/status_schema.md` authoritative
   (add `vendor harness` if missing); extend `test_docs_consistency.py`.
3. Green gate: `uv run pytest -q && uv run ruff check . && uv run mypy src`.

### Acceptance
Artifacts answer the mission questions above; gate is green; docs are consistent.
