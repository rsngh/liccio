# P2/P3 — live scaled arenas (measured)

Live runs executed in this environment within a $25 budget (total live spend ≈ **$4.7**).
All three model providers were reachable; **Gemini is live here**, which the prior committed
reports could not achieve (`"gemini network-unreachable"`). Every number below is from an actual
run, not a projection.

## P2 — Independent proxy verifier as the production stop signal

`reports/independent_proof_eval.json` — corpus scaled to **n=20 tasks × k=5 candidates** (was n=14),
roster mixes Gemini (`gemini-3.1-flash-lite`, `gemini-3-flash-preview`) + Anthropic (`haiku`),
graded by held-out hidden tests:

| selector | verified | cost / verified success |
|---|---|---|
| public-only (today's weak signal) | **0.85** CI[0.64, 0.95] | $0.00874 |
| proxy (independent_proof) | **1.00** CI[0.84, 1.00] | $0.01028 |
| **proxy_stop_signal** (the new production decision) | **1.00** | $0.01028 |
| oracle (upper bound, uses hidden test) | 1.00 | $0.00743 |

- The independent proxy lifts realized verified success **0.85 → 1.00** at **+17.6% cost** — it
  rejects candidates that pass the public test but fail hidden, which public-only promotes.
- The new `verification.proxy_stop_signal.decide` (P1 work) matches the proxy at 1.00 with
  **20/20 confident auto-commits and 0 wrong auto-commits**; its human-review fallback is wired but
  not needed on this corpus because the proxy was perfectly precise here.
- Proxy vs the true hidden oracle over all 100 candidates: **precision = recall = 1.0**
  (tp=91, fp=0, fn=0).

## P2 — Cross-provider heterogeneity arena (Gemini LIVE)

`reports/hetero_arena_xprovider.json` — **20 tasks × 3 trials** (n=60 conclusive/policy), every tier
single-shot live at its real published price:

| policy | verified | cost / verified success |
|---|---|---|
| gemini_flash_lite | 0.80 CI[0.68, 0.88] | **$0.00008** |
| cross_provider_escalation | 0.85 CI[0.74, 0.92] | $0.00024 |
| **haiku** | **1.00** CI[0.94, 1.00] | $0.00131 |
| best_of_providers | 0.85 CI[0.74, 0.92] | $0.00163 |
| sonnet | 0.95 CI[0.86, 0.98] | $0.00336 |
| gemini_flash | 0.85 CI[0.74, 0.92] | $0.00968 |
| gemini_pro | 0.95 CI[0.86, 0.98] | $0.01894 |
| opus | 0.95 CI[0.86, 0.98] | $0.02231 |

- **No model-tier gap on self-contained tasks:** haiku (1.00) matches/beats opus (0.95) at
  **~17× lower cost per verified success** ($0.00131 vs $0.02231).
- **Cross-vendor cheapest-capable wins:** `gemini-3.1-flash-lite` clears 0.80 at **~280× cheaper**
  than opus; `cost_aware_cross_provider_escalation` captures 0.85 at $0.00024 by stopping at the
  cheapest rung that passes public.
- Fixed a real bug surfaced by going live: `tiers.py` pointed `gemini_flash` at a non-existent
  `gemini-3.5-flash` model id → now `gemini-3-flash-preview` (verified via the live `models` API).

## P3 — Live issue-replay with patch-equivalence judging

`reports/issue_replay_live.json` (new runner `evals/issue_replay/run.py`) — a live cheap model
attempts each issue→fix bundle with the **gold patch and hidden tests withheld**, graded by the
held-out hidden test AND semantic patch-equivalence to the gold:

- `gemini-3-flash-preview`: **6/6 hidden-verified**, **5/6 patch-equivalent**, total $0.0014.
- The one non-equivalent case is the LRU *class* bundle, where repr-based equivalence legitimately
  can't corroborate behaviour — reported honestly per-bundle rather than hidden.

## Honest scope / what is NOT claimed

- The capability corpus is **20 tasks** and issue-replay is **6 frozen-synthetic bundles**; this is
  a *scaled live measurement at the available corpus size*, not the GOALS "≥100 tasks / 50 scraped
  real GitHub bundles." Reaching those is bottlenecked by **content** (authoring/scraping
  offline-fair bundles with held-out hidden tests), not compute — the $25 budget was barely touched.
- Bundles remain labelled by source (`frozen_synthetic` vs `real_issue_replay`); no synthetic bundle
  is presented as scraped real history.
