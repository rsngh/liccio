# Alpha 6 — self-improving multi-harness routing lab: PR / merge checklist

Alpha 6 turns the empirical routing *lab* (Alpha 5) into a **self-improving
control plane**: it evaluates new policies offline against logged decisions, trains
a supervised meta-router from trace features, routes context strategy jointly with
the agent, adds vendor coding-agent harnesses, and finishes the real service +
observability backends. Status vocabulary: `docs/status_schema.md`.

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| Foundation | Docker workspace backend v1 (`capture_diff`/`dirty`/`final_head` + configurable network); pluggable vector retrieval (`context.factory` embedder+store selection, `ContextCompiler` auto-select, real pgvector SQL); pre-persist fault injection (`fail_before_node`) + exhaustive resume/idempotency tests. |
| 1 | **Vendor harness category**: `VendorHarnessAdapter` base + `CapabilityRegistry` (deterministic / simple_model / acp_harness / vendor) + capability-gated `claude_agent_sdk` & `codex_cli` shims (registered; self-report unavailable without SDK/binary/key). |
| 2 | **Joint (agent × context-strategy) routing**: the runner recompiles context with the routed strategy so routing drives the *context*, not just the agent; persisted `ContextPack.strategy == RoutingDecision.action.context_strategy`. |
| 3 | **Offline policy evaluation** (`routing/ope.py`): IPS / SNIPS / clipped-IPS / **doubly-robust** with **bootstrap CIs** + diagnostics (ESS, overlap, weight tail). `acp policy evaluate-offline` builds an OPE log from persisted `RoutingDecision` propensities + `RewardEvent`s. Artifact: `evals/reports/ope.json`. |
| 4 | **Supervised meta-router** (`SupervisedRoutingPolicy`): token-generalizing reward predictor implementing `RoutingPolicy` + an OPE target adapter; under OPE it beats random and at least ties the bandit. |
| 5 | **Context-strategy benchmark** (`evaluation/context_strategy_benchmark.py`): sweep strategies × repos for recall@k / MRR / token-cost / latency, best-per-repo selection. CLI `acp eval context-strategy-benchmark`. Artifact: `evals/reports/context_strategy_benchmark.json`. |
| 6 | **Human-review studio backend**: priority-sorted queue filter, `review_bundle` (diff/evidence/weak-label/trace/judge-disagreement summary, secret-free), and `make_eval_case` (label → reusable JSONL eval case). CLI `acp reviews bundle` / `acp reviews make-eval-case`. |
| 7 | **OTLP span exporter** (`observability/otlp.py`, opentelemetry-gated) verified against an in-memory span collector. |
| 8 | **Live OpenAI experiment**: real `openai_harness` solves a no-patch bugfix; committed **redacted** artifact `reports/live/alpha6_openai_experiment.json` (solved + verified, no secret/prompt leak). |
| 9 | This checklist + `ALPHA6_REPORT.md` + `make alpha6-artifacts` + docs-consistency extension. |

## Required artifacts (committed)

- `evals/reports/ope.json` — offline policy evaluation (supervised/greedy beat random under DR).
- `evals/reports/context_strategy_benchmark.json` — per-(repo, strategy) recall@k/MRR/token/latency.
- `reports/live/alpha6_openai_experiment.json` — redacted live OpenAI no-patch solve.

## Gate

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
make alpha6-artifacts
```

## Reviewer questions answered by the artifacts

- If we deploy the supervised meta-router instead of the bandit, what reward
  should we expect? → `ope.json` (DR estimate + bootstrap CI vs logged mean).
- Which context strategy is best per repo, at what token cost? →
  `context_strategy_benchmark.json`.
- Did a real vendor-grade harness actually solve a no-patch task, and at what
  cost/latency? → `alpha6_openai_experiment.json`.
