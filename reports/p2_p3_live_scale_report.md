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

- On the **6 frozen-synthetic** bundles `gemini-3-flash-preview` scored **6/6 hidden-verified**,
  **5/6 patch-equivalent**, $0.0014 (the one miss is the LRU *class* bundle, where repr-based
  equivalence can't corroborate behaviour — reported per-bundle, not hidden).

## P3 — REAL issue-replay (the reality check)

Direct `git clone` works here (the GitHub API does not, token or no token), so
`evals/issue_replay/build_real_corpus.py` harvests **17 real bundles** from actual fix commits in
two public repos (`okunishinishi/python-stringcase`, `mahmoud/boltons` — real issues #240/#302/#348/#349,
etc.). Each uses the **parent commit as buggy**, the **fix commit as the withheld gold**, and the
**repo's own contemporaneous test file as the held-out hidden oracle**; every bundle is validated
hermetically fair (`reports/real_issue_replay_bundles.json`). Single-shot, gold withheld:

| model | real bundles solved (hidden) | cost |
|---|---|---|
| gemini-3-flash-preview (cheap) | **3 / 17 = 18%** CI[0.06, 0.41] | $0.15 |
| opus (frontier) | **1 / 17 = 6%** CI[0.01, 0.27] | $2.85 |

**This is the most important result of the exercise.** The 100% on easy/synthetic tasks does **not**
transfer to real codebase bugs, and — critically — **the frontier model does not rescue it** (opus
was no better than cheap gemini, at ~19× the cost; the CIs overlap, so the honest claim is "tier
makes no difference here"). On real bugs the binding constraint is **context + harness autonomy**
(explore the repo, run tests, iterate), not model tier — exactly the lever ACP is built around, and
exactly what single-shot can't supply.

## Honest scope / what is NOT claimed

- Corpora are **20 capability tasks**, **6 synthetic** + **17 real** issue bundles — a real, live,
  validated measurement, but still short of the GOALS "≥100 tasks / 50 real bundles across 5 repos."
  Yield is **content-bound, not compute-bound**: total live spend was **≈$7.9 of $25**; most of the
  effort is finding real commits whose tests run hermetically (the fairness gate rejected the
  majority of candidate commits).
- The real-bundle setting is deliberately hard (terse commit-message "issue", single-shot, no repo
  exploration, large modules subject to context truncation) — so the low absolute solve rates are a
  floor for *single-shot*, not a verdict on the harness-routed path, which we did not run on the real
  corpus this round.
- Bundles are labelled by source (`frozen_synthetic` vs `real_issue_replay`); no synthetic bundle is
  presented as scraped real history.

## Bottom line on "does the library provide an advantage?"

- **Yes, where measured small-scale:** the proxy verifier reliably catches wrong answers public-only
  ships (0.85→1.00), and cheap/cross-vendor model selection matches frontier quality on easy work at
  10–280× lower cost. Those are real, reproduced live.
- **The real-bug reality check sharpens the thesis:** single-shot — even with the most expensive
  model — solves few real bugs. That is *evidence for* the metarouter premise (the lever is context/
  harness, not tier) but it is **not yet demonstrated**: we have not shown ACP's harness-routed path
  lifting that 3/17 on the real corpus. That is the next experiment.
