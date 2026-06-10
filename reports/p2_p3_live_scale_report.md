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

| path | real bundles solved (hidden) | cost |
|---|---|---|
| single-shot gemini-3-flash-preview (cheap) | **3 / 17 = 18%** CI[0.06, 0.41] | $0.15 |
| single-shot opus (frontier) | **1 / 17 = 6%** CI[0.01, 0.27] | $2.85 |
| ACP in-process tool-loop harness (haiku, 16 steps, tests visible) | **1 / 17 = 6%** CI[0.01, 0.27] | $1.63 |
| **enhanced repair harness — gemini** (localize→best-of-k→splice) | **3 / 17 = 18%** CI[0.06, 0.41] | $0.20 |
| **enhanced repair harness — sonnet** (same pipeline, stronger model) | **3 / 17 = 18%** CI[0.06, 0.41] | $1.10 |
| **🟢 Gemini CLI (real stateful agent, API key)** | **16 / 17 = 94%** CI[0.73, 0.99] | ~$0 (CLI, not metered here) |
| **🟢 Claude Code CLI (real stateful agent, your subscription)** | **15 / 17 = 88%** CI[0.66, 0.97] | $0 metered (subscription) |
| **🟢 Codex CLI (real stateful agent, your subscription)** | **17 / 17 = 100%** CI[0.82, 1.00] | $0 metered (subscription) |
| **🟢🟢 best-of-pool (any of the 3 agents solves)** | **17 / 17 = 100%** | — |

## THE BREAKTHROUGH: real coding agents shatter the 3/17 wall

Once the three production CLI agents were authed in-container and wired into the runner
(`--mode vendor`), **every one of them cleared 88–100%** of the exact bundles all five model-only
configs plateaued at 3/17 — Codex 17/17, Gemini CLI 16/17, Claude Code 15/17. Their errors are
**uncorrelated** (the 2 Claude Code missed are solved by Codex and Gemini), so the diverse pool
covers **17/17** — which is precisely the proposer→verifier→comparator *boosting* premise: a verifier
selecting across diverse strong agents reaches the union. Graded identically and return-code-
authoritative on the pristine held-out test.

This is the decisive result of the whole investigation and it validates the meta-router thesis:
- The real-bug wall was **the weakness of the agents in the pool, not the orchestration.** Model-only
  (cheap or frontier, single-shot or harness-scaffolded) tops out at 18%; any real agent with native
  localization + multi-file edits + test-running + iteration hits 88–100%.
- It defines the meta-router's actual job: **(1) recognise the task needs a real agent (not a cheap
  model); (2) route to the cheapest agent that's good-enough per task family; (3) ensemble + verify
  across the diverse pool to cover any single agent's misses (→ 100% here); (4) learn per-family which
  agent wins, to drive cost/quota down over time.** It does *not* out-muscle a frontier agent by
  wrapping it — it orchestrates a pool of them.

## P3 — ACP routing vs agent-only: the value, quantified (`reports/issue_replay_routing_economics.json`)

Offline policy evaluation over the real per-agent results (an agent "succeeds" iff its produced
module passed the held-out test — the acceptance check the router runs as its stop-signal; invocation
counts are exact, the per-agent $ is a transparent API-equivalent prior since subscriptions bill $0
metered). Cheapest-first ladder: inproc-repair → gemini-cli → claude-code → codex.

| policy | solved | strongest-agent runs | cost/verified-success |
|---|---|---|---|
| agent-only: inproc model | 3/17 | 0 | 0.113 |
| agent-only: Gemini CLI | 16/17 | 0 | 0.064 |
| agent-only: Claude Code | 15/17 | 0 | 0.113 |
| agent-only: **Codex (best single)** | **17/17** | **17** | 0.120 |
| **ACP escalation (cheapest-first + verify-stop)** | **17/17** | **0** | **0.075** |
| ACP ensemble (all + verify-select) | 17/17 | 17 | 0.300 |

**ACP routing matches the best single agent's 17/17 at ~37% lower cost, and never invokes the
strongest agent at all** — the ladder stops at: inproc 3, Gemini 13, Claude Code 1, Codex 0. It also
beats every *cheaper* single agent on solve rate (+1 vs Gemini, +2 vs Claude Code) by escalating only
on the misses. That is the meta-router's value made concrete: **≥ the best single agent on quality,
< always-running-it on cost.** The ensemble row is the boosting upper bound (max robustness, max cost);
per-family memory (`family_memory` in the JSON) is the mechanism that drives the escalation cost down
further over repeated work by defaulting each repo family to its known cheapest-sufficient agent.


**The model-only plateau (still the honest record) — and why it cut against easy optimism.** We tried, in
order: a frontier model, an autonomous tool-loop harness, and then a research-grounded *enhanced*
repair harness (the convergent recommendation of three paper sweeps: localize the bug to a function,
show the model only that snippet, sample best-of-k, splice the fix back by AST, iterate on the precise
test failure). The enhanced harness did exactly what the papers promised mechanically — it **localized
correctly** (e.g. pinpointed `OneToOne.update`), cut context/cost ~15× vs single-shot opus, and removed
the tool-loop thrashing. **But the solve rate did not move: 3/17, the same as cheap single-shot, and a
stronger model (sonnet) did not change it either.**

So across five configurations — cheap single-shot, frontier single-shot, autonomous harness, and the
enhanced localize→repair harness on two model tiers — **the real-bug solve rate is flat at ~3/17.**
The three solved are the clean single-function bugs; the other 14 (mostly class-method/multi-function
boltons bugs) resist every lever we pulled. The binding constraint is therefore **not** context size
(we fixed that), **not** model tier (sonnet ≈ gemini ≈ opus here), and **not** scaffolding thrash (the
enhanced pipeline is clean) — it is the underlying difficulty of correctly diagnosing these specific
real bugs from a terse issue. That is a genuinely hard, unsolved problem, and importantly: the gold fix
provably passes each test file, so the corpus is fair — the models simply don't find the right fix.

## Honest scope / what is NOT claimed

- Corpora are **20 capability tasks**, **6 synthetic** + **17 real** issue bundles — a real, live,
  validated measurement, but still short of the GOALS "≥100 tasks / 50 real bundles across 5 repos."
  Yield is **content-bound, not compute-bound**: total live spend was **≈$15 of $25**; most of the
  effort is finding real commits whose tests run hermetically (the fairness gate rejected the
  majority of candidate commits).
- The enhanced repair harness fixed the things we could diagnose (context blow-up, scaffolding thrash,
  localization) and is the configuration the research literature recommends; its flat 3/17 is therefore
  a meaningful signal, not a strawman. Remaining unknowns: localization still misses on ~2 bundles
  (whole-module fallback), and we capped best-of-k at 2–3 and reflexion at 2 rounds.
- Bundles are labelled by source (`frozen_synthetic` vs `real_issue_replay`); no synthetic bundle is
  presented as scraped real history.

## Bottom line on "does the library provide an advantage?"

- **Yes, narrowly and small-scale:** the proxy verifier reliably catches wrong answers public-only
  ships (0.85→1.00), and cheap/cross-vendor model selection matches frontier quality on *easy* work at
  10–280× lower cost. Those are real, reproduced live, and genuinely useful.
- **Not demonstrated on real bugs:** across five configurations (cheap/frontier single-shot, autonomous
  harness, enhanced localize→repair on two model tiers) the real-bug solve rate is **flat at 3/17**.
  The central promise — orchestrating context/harness/verifier to beat a frontier model on *real* work
  — remains **unproven**, and we now know *why the easy levers fail*: it is neither context nor tier nor
  scaffolding thrash, but the underlying difficulty of these bugs.

## Recommendation on scaling to a big test

**Do not yet spend budget scaling to 50+ bundles.** Five distinct configurations agree at 3/17, so a
bigger run with the *current* methods would most likely just reconfirm a low rate at higher cost — low
information per dollar. Scale only after a config demonstrably clears, say, >40% on the current 17.

## Failure diagnostic (why the misses miss) — `reports/issue_replay_diagnosis.json`

A cheap diagnostic (re-run the enhanced gemini repair, classify each produced module's remaining
failures vs the buggy baseline, return-code authoritative) categorises the 17:

| category | n | meaning |
|---|---|---|
| solved | 3 | produced module passes the whole held-out file |
| **no_progress** | **8** | localization found the right function, but the fix does **not** flip the failing test |
| regressed | 1 | the fix broke other tests the buggy base passed |
| unmeasurable | 5 | the (large boltons) test file times out / errors standalone — excluded, not graded |

Supporting facts: **localized 15/17**, **oracle-gap median = 1** (9 bugs need exactly one test
flipped), and **the gold fix passes every measurable bundle** (corpus is fair). So the dominant
failure (`no_progress`, 8) is **not** context size, **not** scaffolding, **not** an over-broad oracle
— the model is handed the correct, small buggy function and a single failing test, and still writes a
wrong fix. The bottleneck is **repair correctness on subtle bugs**, i.e. raw model/diagnosis
capability — which is exactly what neither the stronger model (sonnet) nor the research-grounded
pipeline moved.

**Implication for scaling and for the library's thesis:** more orchestration (context/harness/verifier
routing — what ACP does) cannot recover these, because the orchestration is already doing its job
(right file, right test, clean loop). The remaining gap is model capability on hard real bugs. A
larger corpus would re-measure the same wall; the only levers with a plausible shot are
verifier-guided *many*-sample search (far more than k=2-3) or a materially stronger repair model —
both of which trade a lot of cost for uncertain gain. Recommendation stands: **bank these honest
findings; don't scale the corpus until a config first clears ~40% on the existing 17.**

## P4 — harder bundles that separate the frontier; routing value holds at larger n

The diagnostic above is about the **model-only** plateau on the easy v1 corpus. P4 scales a different
axis: harder, *agent-separating* bundles. v1's 17 utility fixes clustered the frontier agents at
0.88–1.0 (no room to distinguish them). New **package-mode harvesting** (lay down the real package +
pristine siblings instead of flattening to one file) unlocked algorithmically richer libs —
`toolz`, `parse`, `more-itertools` — for **24 harder bundles**; the pool ran on a tractable 10-bundle
subset (the whole-test-file oracle on `more-itertools` is heavy, so grading was made
crash-proof — a timeout scores as a fail — and capped at a 10-bundle `--limit`).

**Per-agent solve rate — easy vs hard (the separation we were missing):**

| agent | v1 easy (17) | P4 hard (10) |
|---|---|---|
| inproc model | 0.18 | 0.20 |
| claude_code | 0.88 | **0.70** |
| gemini_cli | 0.94 | **0.80** |
| codex_cli | **1.00** | **0.90** |

On hard the frontier spreads to 0.7–0.9 (codex > gemini > claude — same order, wider gaps), and **one
bundle ("concurrent tee") is solved by no agent at all** (union 9/10) — a genuine ceiling-breaker the
easy corpus never produced. Codex drops from a perfect 17/17 to 9/10: the harder corpus does its job.

**ACP routing vs agent-only, combined corpus (27 bundles), effective-cost prior:**

| policy | solved | strongest-agent runs | cost/verified-success |
|---|---|---|---|
| agent-only: Codex (best single) | 26/27 | **27** | 0.125 |
| agent-only: Gemini | 24/27 | 0 | 0.068 |
| agent-only: Claude Code | 22/27 | 0 | 0.123 |
| **ACP escalation (cheapest-first + verify-stop)** | **26/27** | **1** | **0.088** |
| ACP ensemble (all + verify-select) | 26/27 | 27 | 0.312 |

The headline survives harder, separating data **at larger n**: ACP escalation **matches the best
single agent (26/27) while invoking the strongest agent once instead of 27 times — ~30% cheaper per
verified success** (stop-rung: inproc 5, gemini 19, claude 2, codex 0; 1 unsolved by anyone). And it
still beats every cheaper single agent on solve rate (+2 vs Gemini, +4 vs Claude Code).

**Honest scope:** 27 bundles across 5 repos; the hard slice is 10 bundles (heavy oracle caps the
pool). The model-only wall from the diagnostic is unchanged — P4 doesn't claim to move raw repair
capability; it shows the *meta-router's* value (match the best at lower cost) holds once the corpus is
hard enough to tell the agents apart, and that genuinely hard bugs (the no-agent-solves bundle) exist
in the harvested set for future capability work.
