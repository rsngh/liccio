# Alpha 44 — Hard-Realism MetaRouter

**Date:** 2026-06-07 · **Anthropic-only** (OpenAI/Gemini are mocked hooks; no live claim).

## Mission result: the ceiling is defeated

Alpha 43 was honest but ceiling-bound: a frontier model solved easy/medium tasks from minimal
context, so no policy beat `cheap_single` with CI separation. **Alpha 44 built tasks hard enough
to break that ceiling and proved metarouting wins — with statistical confidence — exactly where
the task is genuinely hard.**

### The hard arena (P0) — 654 live conclusive cells, all gates pass

109 unseen hard tasks across 11 families × 6 policies = **654 conclusive cells (100% conclusive)**.
The ceiling-breaker family puts a **non-guessable constant in an unreferenced helper file**, so
the fix is unobtainable from the buggy file alone. Result:

| Policy | verified | 95% Wilson CI |
|---|---|---|
| repo_map_router | 0.88 | [0.81, 0.93] |
| grep_router | 0.87 | [0.80, 0.92] |
| abstain_router | 0.87 | [0.80, 0.92] |
| **cheap_single** (incumbent) | **0.39** | **[0.30, 0.48]** |
| oracle (ceiling) | 1.00 | [0.97, 1.00] |
| cheap_static (floor) | 0.11 | [0.06, 0.18] |

`cheap_single` collapses from 0.89 (Alpha 43 easy arena) to **0.39** here, with **67 failures** —
the ceiling is gone. The routed policies now beat it with **non-overlapping CIs both globally and
per bucket** (the Alpha-44 thesis):

| Bucket | grep / repo_map | cheap_single |
|---|---|---|
| cross_file_api (49 tasks) | **1.00** | 0.10 |
| broad_repo_map (12 tasks) | **0.83** | 0.00 |

All 7 acceptance gates pass: ≥600 cells, ≥100 tasks, ≥10 families, ≥5 context-needs, ≥25
cheap_single failures, **0 high-risk false auto-approve**, **≥1 bucket-level CI-separated win**.

### Executable topology controller — LIVE (P2)

Beyond Alpha 43's offline search: a controller that **executes** an escalation ladder
(cheap_single → retry_with_grep → retry_with_repo_map) with hard safety invariants. On a hard
ceiling-breaker subset, **the controller verifies 1.00 vs cheap_single's 0.17** — escalation
rescues every task the incumbent fails. Safety enforced: high-risk/security must pass a strict
verifier before commit; forbidden-file candidates are never committed; unsolved high-risk routes
to human, never blind auto-approve.

## Workstreams (all committed, tested, with artifacts)

| P | Workstream | Result |
|---|---|---|
| P0 | Hard-realism arena | **654 cells, ceiling defeated, bucket-level CI wins** (`hard_realism_arena.json`) |
| P1 | Issue replay (offline-first) | 6 frozen bundles, all offline-fair, patch-equivalence judge; honestly `frozen_synthetic` |
| P2 | Executable topology controller | **live 1.00 vs 0.17**; safety invariants (`topology_live_ablation.json`) |
| P3 | Advisor v3 calibration | consults only where marginal value > 0 |
| P4 | Best-of-k v3 diversity | diverse arms rescue tasks naive same-prompt k fails |
| P5 | Context experiment matrix | **embedding tested honestly**; repo_map 25 vs grep/embedding 3 coverage/token; grep-vs-embedding a measured tie |
| P6 | Memory lifespan (100 sessions) | memory 60 vs 39 baseline; revision recovery after a mid-history migration; poisoning quarantined |
| P7 | Harness evolution guarded PRs | 3 proposals from real failure clusters → 1 promoted, 1 rejected (negative transfer), 1 rejected (no lift) |
| P8 | Production-ish deploy gate | 100 concurrent jobs, unique run IDs, no orphans, `production_ready` |
| P9 | Operator learning loop | label changes future routing; disagreement blocks; high-risk stays advisory |
| P10 | Provider marketplace | anthropic `live_conclusive`; OpenAI/Gemini `mock_contract_only`; mix recommends only feasible |
| P13 | Claim checker | **12/12 claims supported** (`claim_evidence_map_alpha44.json`) |

## Hard rules honored

- Unavailable provider ≠ capability failure; OpenAI/Gemini mocked hooks only, no live claim.
- No contaminated sample entered capability/OPE/promotion (100% conclusive).
- No high-risk task skipped strict verification; 0 high-risk false auto-approve.
- No promotion without CI separation (global + bucket-level, Wilson-separated).
- Every headline claim maps to fresh, uncontaminated evidence (claim-check 12/12).

## Honest limitations / deferred

- Issue-replay bundles are **frozen synthetic-realistic**, not scraped history (no network for
  real GitHub ingest); the schema + runner are exactly what an online ingestor would feed, and
  the tier is labeled so a synthetic bundle can never masquerade as `real_issue_replay`.
- The harness-evolution canary signals and the deploy gate are **in-process simulations** (the
  governance/invariant logic is real and tested; full k8s/compose stand-up is deferred).
- The 654-cell arena used single-shot live policies + deterministic baselines; the advisor and
  best-of-k v3 are exercised as live ablation / deterministic modules, not yet at 654-cell scale.

## Bottom line

Alpha 43 made ACP honest; **Alpha 44 makes it undeniably differentiated where it counts.** On
hard, hidden-tested, unseen tasks a strong cheap baseline scores 0.39, and ACP's context-routing
and executable escalation beat it to ~0.88–1.00 with non-overlapping confidence intervals,
globally and per bucket — proven with 654 conclusive live cells, bucketed promotion, and a claim
checker that refuses to overclaim.
