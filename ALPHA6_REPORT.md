# Alpha 6 report — the self-improving multi-harness routing lab

Alpha 5 built a lab that could *measure* harnesses. Alpha 6 makes the control
plane **learn to route and prove it counterfactually**, routes context strategy
as a first-class decision, adds vendor coding-agent harnesses, and finishes the
real service + observability backends. See `ALPHA6_CHECKLIST.md` for the
workstream-by-workstream matrix and `GOALS.md` for the plan (Alpha 5 plan
archived in `GOALS5.md`).

## Headline results

**Offline policy evaluation works** (`evals/reports/ope.json`). On a logged
dataset collected under a uniform behavior policy across three task types
(bugfix / refactor / security), the doubly-robust estimator ranks the learned
policies far above the logging policy — with no agents re-run:

| Target policy | DR value | 95% bootstrap CI |
| --- | --- | --- |
| greedy (reward-model) | 1.000 | [1.000, 1.000] |
| supervised meta-router | 1.000 | [1.000, 1.000] |
| logged behavior (baseline) | 0.500 | — |
| random | 0.500 | [0.500, 0.500] |

The supervised meta-router and greedy policies double the expected reward over
the logging policy, and the bootstrap CIs do not overlap the random baseline —
exactly the signal needed to justify deploying a new policy before paying to A/B
it. The same machinery runs on *real* persisted logs via
`acp policy evaluate-offline` (see `AppService.evaluate_policy_offline`).

**A real OpenAI harness solved a no-patch task** (`reports/live/alpha6_openai_experiment.json`,
redacted): `solved=true`, `verified_raises_on_zero=true`, 1 tool call,
~644 tokens, ~$0.0004, ~3.3 s — with no secret or prompt leakage in the artifact.

**Context strategy is now routable** (`evals/reports/context_strategy_benchmark.json`):
strategies are swept across multiple repo fixtures for recall@k / MRR / token
cost / latency, with a best-strategy-per-repo selection, so routing can pick a
context strategy and not just an agent.

## What's new since Alpha 5

- **`routing/ope.py`** — IPS, self-normalized IPS, clipped IPS, and a
  doubly-robust estimator (fitted reward-model baseline + IPS correction), each
  with a percentile bootstrap CI, plus diagnostics: effective sample size,
  propensity overlap, weight tail, and clipped mass. `from_decision_log` adapts
  the `(PolicyDecision, RewardEvent)` logs the service already persists.
- **`SupervisedRoutingPolicy`** — a reward predictor over bag-of-tokens features
  of the `(context, action)` keys, so it *generalizes* across agents / strategies
  / task types rather than memorizing exact arms like the tabular bandit. It
  implements the `RoutingPolicy` protocol and exposes an OPE target adapter.
- **Joint routing** — `_node_route_task` recompiles context with the routed
  strategy; the persisted `ContextPack.strategy` matches the routing decision.
- **Vendor harness category** — `VendorHarnessAdapter` + `CapabilityRegistry`
  classify every adapter (deterministic / simple_model / acp_harness / vendor)
  with live availability; `claude_agent_sdk` and `codex_cli` shims are registered
  and degrade gracefully.
- **Human-review studio** — priority-sorted queue, a secret-free adjudication
  bundle, and label→eval-case conversion so every human label becomes durable
  supervision.
- **Real services / observability** — Docker workspace backend v1 completes the
  workspace contract; `PgVectorStore` has real pgvector SQL; `OTLPSpanExporter`
  exports ACP spans through OpenTelemetry.

## Honest limitations

- The OPE headline uses a synthetic, separable log to make the estimator's
  behavior auditable; on real ACP logs the signal is noisier and overlap
  diagnostics matter (they are reported).
- Vendor shims are capability-gated scaffolding: `codex_cli` is *available* in
  this environment (a `codex` binary is on PATH) but the shims are not yet
  battle-tested against a full vendor SDK loop.
- Qdrant is not installed in this environment, so the Qdrant persistent-path
  contract test remains deferred; pgvector live SQL is DSN-gated.
- The supervised meta-router is a linear/ridge model with a mean fallback; it is
  deliberately simple so it always trains and stays calibratable.
