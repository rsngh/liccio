# Alpha 7 report — policy-governed routing + a training pipeline from exhaust

Alpha 6 made the control plane *self-improving* (offline policy evaluation +
supervised meta-router). Alpha 7 makes it *policy-governed*: it decides what is
viable to attempt, only promotes a routing policy that provably passes a safety
gate, and turns every run into redacted, leakage-audited training data. See
`ALPHA7_CHECKLIST.md` for the workstream matrix; `GOALS.md` for the plan (Alpha 6
plan archived in `GOALS6.md`).

## The acceptance question

> Can ACP look at a request, decide what is viable, choose agent + model +
> context + verifier, prove the policy offline, run safely, produce training
> data, and improve a local classifier/evaluator from the exhaust?

Alpha 7 answers each clause with a concrete, tested mechanism.

## Headline results

**The OPE promotion gate blocks unsafe policies and promotes safe ones.** On the
committed `evals/reports/real_log_ope.json` (a logged dataset under a uniform
behavior policy):

| Policy | DR value | Promotion gate |
| --- | --- | --- |
| random | 0.50 | — (baseline) |
| greedy (deterministic) | 1.00 | **BLOCKED** — propensity overlap 0.50 < 0.80 |
| supervised (deterministic) | 1.00 | (same overlap risk) |
| supervised (exploration-smoothed) | 0.98 | **PROMOTE** — full overlap, DR CI [0.979, 0.979] ≫ baseline → staged canary plan |

This is the central Alpha-7 result: a naive greedy policy with a sky-high point
estimate is **correctly refused** because it never overlaps half the log, while
an exploration-preserving policy with a marginally lower estimate but trustworthy
diagnostics is promoted. Decision *quality*, not just decision *value*.

**Viability is decided before action.** Every run now carries a
`ViabilityAssessment`: docs/low-risk work → a cheap simple-model adapter is
viable; security/high-risk → true harness + strict verification + human review;
no spec / no tests → **abstain** and require spec inference first. It is
persisted and consumed by routing to narrow the context-strategy space.

**A real OpenAI run becomes governed + training data.**
`reports/live/alpha7_openai_experiment.json` (redacted) shows the full slice:
viability assessed, the real `openai_harness` solved and *verified* the no-patch
bugfix (~$0.0004, no secret/prompt leak), and a redacted `repair` training
example was distilled from the diff.

**The capability matrix refuses to overclaim.** `viability_matrix.json` builds
per-routing-tuple cells from a bakeoff report and flags any cell below the
minimum sample size, so `best_for` never recommends an under-sampled arm.

**The training factory is honest about readiness.**
`training_candidate_report.json` recommends fine-tuning only when sample size and
a clean leakage audit justify it (currently `recommend_finetune=false` on the
synthetic corpus — correctly conservative).

## What's new since Alpha 6

- `schemas/viability.py` + `core/viability.py` + persistence + routing consumption.
- `routing/promotion.py` — the OPE promotion gate (statistical + operational
  conditions, canary plan) and `AppService.policy_promotion_check`.
- `AppService.real_log_ope_report` — multi-policy comparison on real logs with a
  trust gate.
- `routing/capability_matrix.py` — empirical capability matrix with low-sample
  flagging.
- `training/` — dataset factory (split/dedup/redaction/leakage audit), JSONL
  exporters, candidate report, gated LoRA smoke; `AppService` wiring + CLI.
- `evaluation/context_downstream_benchmark.py` — strategy benchmark by downstream
  success.
- Hardened `codex_cli` vendor harness; review-studio `make_training_example`.

## Honest limitations

- The OPE headline uses a synthetic, separable log so the gate's behavior is
  auditable; `real_log_ope` runs the same machinery on real logs but will report
  `trustworthy=false` until enough exploratory traffic is logged.
- Vendor harnesses: `codex_cli` is a real mediated loop in shape but is not yet
  proven against a full production codex session; `claude_agent_sdk` remains
  capability-gated scaffolding.
- LoRA fine-tuning is a gated smoke path (no GPU here); the pipeline produces and
  audits the data and *recommends* when to train, but does not train in CI.
- The viability assessor is deterministic rules (no learned classifier yet) — a
  natural next target for the training factory's `viability` dataset kind.
