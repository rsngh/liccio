# Alpha 43 — Scale-Proven MetaRouter + Evidence Freshness

**Date:** 2026-06-07 · **Anthropic-only** (OpenAI/Gemini are hooks + mocked contracts).

## Mission result

Alpha 42 proved the MetaRouter *shape* at smoke scale. **Alpha 43 proves it at statistical
scale and makes overclaiming impossible by construction.** The scaled arena ran **53 unseen,
hidden-tested tasks × 6 policies = 318 conclusive cells (100% conclusive)** on live Claude, with
Wilson confidence intervals and a claim checker that binds every headline claim to fresh,
uncontaminated evidence.

## P0 — Scaled MetaRouter Arena (the keystone)

All acceptance gates pass (`reports/metarouter_arena_scaled.json`):

| Gate | Required | Actual |
|---|---|---|
| conclusive cells | ≥300 | **318** |
| tasks | ≥50 | **53** |
| task types | ≥8 | **8** |
| context-need classes | ≥5 | **5** |
| conclusive rate | ≥80% | **100%** |
| high-risk false auto-approve | 0 | **0** |

Verified success per policy, with 95% Wilson CIs:

| Policy | verified | 95% CI | $/verified success |
|---|---|---|---|
| `grep_router` | 0.98 | [0.90, 1.00] | **$0.00136** (cheapest) |
| `abstain_router` | 0.96 | [0.87, 0.99] | $0.00171 |
| `repo_map_router` | 0.96 | [0.87, 0.99] | $0.00150 |
| `cheap_single` (incumbent) | 0.89 | [0.77, 0.95] | $0.00158 |
| `oracle` (ceiling) | 1.00 | [0.93, 1.00] | $0 |
| `cheap_static` (floor) | 0.00 | [0.00, 0.07] | — |

### The honest scientific finding

**No policy beats `cheap_single` with confidence-interval separation** at n=53, so
`promotable_with_confidence = []` and the arena **refuses to promote**. The point estimates favor
grep/repo_map/abstain (all ≥0.96), but their CIs overlap the incumbent's [0.77, 0.95]. Two real
effects drive this, and both are reported rather than hidden:

1. **Ceiling effect.** A frontier model (Sonnet 4.6) solves most of these tasks from *minimal*
   context (0.89 baseline), compressing the gap that was stark on the hand-built smoke task
   (0/3→3/3). Bigger separation needs harder tasks (P11) — not a bigger model.
2. **Grep ≥ repo_map at scale.** `grep_router` (raw cross-file content) edges `repo_map_router`
   (signatures) across context-needs — consistent with "Is Grep All You Need?". `context_strategy_ope_v2`
   routes most buckets to grep. ACP measures this rather than defaulting to embeddings.

This is exactly the rigor the round demanded: *every policy promotion must beat a static baseline
with confidence intervals or remain advisory.*

## Workstreams delivered

| P | Workstream | Modules | Artifacts |
|---|---|---|---|
| P0 | Scaled arena (≥300 cells, CIs, cell accounting, failure taxonomy) | `evals/metarouter_arena/{task_loader,statistics,scaled_runner}.py` | `metarouter_arena_scaled.json`, `metarouter_{cell_accounting,confidence_intervals,failure_taxonomy,policy_compare_scaled}.json` |
| P2 | AdvisorPolicy v2 — calibrated marginal-value triggers | `routing/advisor_calibration.py`, `finops/advisor_marginal_value.py` | (logic + tests) |
| P5 | Context bandit + ContextStrategyOPE v2 | `context/context_bandit.py` | `context_strategy_ope_v2.json` |
| P6 | Memory v2 — ablation, privacy red-team, revision audit | `memory/experience_bank.py` (v2 fields) | `memory_v2_ablation.json`, `memory_privacy_redteam.json`, `memory_revision_audit.json` |
| P7 | FinOps v2 — marginal-value controller + provider market | `finops/marginal_value_controller.py` | `finops_marginal_value.json` |
| P8 | Provider abstraction + mocked OpenAI/Gemini contracts | `src/acp/providers/*` | `provider_contract_gate.json` |
| P13 | Claim checker / evidence freshness | `src/acp/reports/*` | `claim_evidence_map.json` (**8/8 supported**) |

### Selected measured results

- **Memory v2:** cost/verified-success **$0.0079 → $0.0034** on repeated failure-signatures;
  cross-tenant reads blocked; a post-merge revert revises memory (`reverted` strategy avoided).
- **Provider contracts:** all 5 providers pass the contract; OpenAI/Gemini mocked-available with
  **no network**; unavailable ⇒ infra-not-capability.
- **Advisor v2 / FinOps:** advisor/best-of-k/retry spend gated by positive marginal value within
  budget class; no-op advisor calls flagged as waste.

## DoD command surface

```bash
uv run python evals/metarouter_arena/scaled_runner.py     # or: acp arena run
acp arena compare ; acp finops report ; acp context strategy-ope
acp provider health --show-unavailable
acp reports claim-check          # 8/8 claims supported
acp health --mode production
```

## Honest limitations / deferred

- The scaled run used **single-shot live policies** (cheap/grep/repo_map/abstain) + deterministic
  baselines to reach 318 cells affordably; the tool-loop harness, advisor, and best-of-k policies
  are exercised in the smaller arena and as deterministic v2 modules, not yet at 318-cell scale.
- **Deferred to later sprints (scaffolding noted):** P1 real GitHub issue-replay bundles, P3
  best-of-k v2 diversity/pruning live, P4 executable topology controller live, P9 production
  k8s/queue deploy gate, P10 operator learning loop, P11 hard research-engineering benchmark,
  P12 harness-evolution guarded-PR loop. These are genuinely multi-sprint; this round delivered
  the scale-proof + evidence-freshness core the mission prioritized.

## Bottom line

ACP now has a **scaled (318-cell), hidden-tested, confidence-interval'd** arena; a **claim
checker** that blocks any stale/contaminated/fixture-only overclaim (8/8 claims pass); and a
**provider abstraction** that keeps OpenAI/Gemini as honest hooks. The headline is not a hype
number — it is a *rigorous* one: at this scale the routed policies are excellent (≥0.96) but not
yet CI-separated from a strong cheap baseline, and ACP says so.
