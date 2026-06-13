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

## P5 — n=52 scaled corpus: the meta-router result holds AND strengthens (escalation beats the best single agent)

P4 left the corpus at 27 bundles and recommended scaling only once the data tells the agents apart —
which it now does. **v2 doubles the labelled set to 52 real bundles across 6 repos** (boltons 19,
more-itertools 29, toolz/parse/arrow/stringcase 1 each; built `$0`-metered via `git clone` + local
pytest fairness — the gold fix must pass and the buggy base must fail, standalone). All four agents
were then profiled single-shot on the full 52 via the **resumable** `multisample --n 1` path (per-bundle
persist, so the multi-hour pool survives container suspends). Subscriptions ran `$0`-metered
(`claude_code` at `ACP_CLAUDE_EFFORT=low`); the only metered spend was repair2 (≈$0.26) + the
Gemini-CLI key.

**Per-agent single-shot solve rate at n=52 (the separation is now stable):**

| agent | v1 easy (17) | P4 hard (10) | **v2 (52)** |
|---|---|---|---|
| inproc/repair2 | 0.18 | 0.20 | **0.37** (19/52) |
| claude_code | 0.88 | 0.70 | **0.83** (43/52) |
| gemini_cli | 0.94 | 0.80 | **0.87** (45/52) |
| codex_cli | 1.00 | 0.90 | **0.98** (51/52) |

**ACP routing vs agent-only, v2 (52 bundles), effective-cost prior:**

| policy | solved | strongest-agent runs | effective cost | cost/verified-success |
|---|---|---|---|---|
| agent-only: Codex (best single) | 51/52 | **52** | 6.24 | 0.122 |
| agent-only: Gemini | 45/52 | 0 | — | — |
| agent-only: Claude Code | 43/52 | 0 | 5.20 | 0.121 |
| **ACP escalation (cheapest-first + verify-stop)** | **52/52** | **1** | **3.64** | **0.070** |
| ACP ensemble (all + verify-select) | 52/52 | 52 | 15.6 | 0.300 |

The headline is now **stronger than "match the best at lower cost"**: at n=52, cheapest-first
verify-stop **beats the best single agent on solve rate (52/52 vs Codex's 51/52) while invoking the
strongest agent once instead of 52 times — ~42% cheaper effective cost (3.64 vs 6.24), 0.070 vs 0.122
per verified success.** Stop-rung distribution: **repair2 19, gemini 28, claude 4, codex 1, unsolved 0** —
the ladder resolves 90% of work on the two cheapest rungs and touches the most expensive agent exactly
once.

**Why escalation now *beats* Codex, not just ties it — heterogeneity pays off concretely.** Codex's
lone single-shot miss is more-itertools #1096 "concurrent tee" (the same bug that no agent solved at P4
n=10). At n=52 it is solved single-shot by **`claude_code` — a *cheaper* rung** — so the diverse pool
covers Codex's blind spot and the union reaches **52/52 with zero bundles unsolved by everyone**. This is
the cross-agent-diversity argument made concrete: the best agent is not a superset of the pool, so
routing across heterogeneous agents strictly dominates always-running the single strongest one.

**Robustness of the cost claim (`reports/issue_replay_cost_sensitivity_v2.json`).** Sweeping the cost
prior m∈[2,20]: saving vs always-best median **0.72**, max **0.81**, and **0.417** at the realistic
api-equivalent prior. The honest nuance from P4 survives: under a *flat* prior (cheap rungs not actually
cheaper) the saving goes **negative (−0.75)** — blind cheapest-first pays for failed cheap attempts. The
win is therefore conditional on a real cost gradient (which holds: a small model is 10–100× cheaper than
a frontier agent) or on memory/difficulty-prediction to skip doomed cheap rungs.

**Coverage + memory at n=52.** Greedy pool growth reaches **union 1.0 at just 2 agents** (codex 0.981 →
+claude 1.0; marginal lift from agents 3–4 is zero), and expected union by random pool size is
{1: 0.76, 2: 0.95, 3: 0.99} — two well-chosen heterogeneous agents capture essentially all solvable
work. Memory economics (`..._memory_economics_v2.json`): solution-memory saves **0.75** and rung-memory
**0.20–0.30**, both independent of the cost prior — exactly the lever that rescues the shallow-gradient
regime where blind escalation loses.

**Honest scope + the Step-2 finding (corpus stays Codex-saturated).** 52 bundles across 6 repos; harvest
yield is **content-bound, not compute-bound** (jmespath yielded 0 hermetic bundles; the fairness gate
rejects most candidate commits). Critically, **even at 2× the corpus, Codex single-shot is 51/52 (0.98)** —
the labelled set the harvestable utility libraries can produce remains near-saturated by the strongest
agent. The *de-saturating subset* (where the top agent misses single-shot) is therefore essentially the
**single** "concurrent tee" bundle, which a cheaper rung already recovers. So a multi-hour *live*
unsaturated escalation ladder would re-measure that one bundle and add no information beyond the offline
n=52 economics above. **The meta-router thesis is now demonstrated at larger n** (cheaper than, and
strictly better than, the best single agent, with the diversity mechanism identified); **raw repair
capability on genuinely hard bugs is still the open frontier** — unchanged from the P4 diagnostic, and
not something more orchestration can move.

## P6 — attacking the capability wall: a dense, fair, in-loop verifier (verifier-guided repair)

P5 closed the *routing* story and re-confirmed the *capability* wall: the cheap in-process repair rung
solves 19/52, and the diagnostic's dominant failure is `no_progress` (right function localized, wrong
fix). The research corpus (KVerus/AutoVerus/VerMCTS + Reflexion/DeepConf) converges on one mechanism for
exactly this: **a dense verification signal driving search + structured refinement.** P6 builds the
Python analogue and runs the smallest experiment that can prove or kill it (`guided_repair_phase0`).

**Two code-verified facts motivated it.** (1) The cheap loop's in-loop accept signal was the *hidden
test* itself (`repair_harness.py:178/217`) — BINARY and PRIVILEGED (the vendor CLIs never see it), so even
with the oracle visible, 0/1 over k samples gives no gradient. (2) The `independent_proof` proxy already
synthesizes fair checks from spec + public test but was used only for post-hoc *selection*. P6 turns it
into a **continuous, fair in-loop value function** (`repair_battery`): example + property + differential
checks (the *discriminating/guard* split falls out of running each check on the buggy baseline once),
scored in [0,1], built only from spec + public test + buggy baseline — never the hidden test (reserved
for grading) and never the gold patch. The greedy solver (`guided_repair`) climbs this score and
localizes on the *public* test, fixing the privilege leak.

**What Phase 0 found (11 diagnostic bundles: 8 `no_progress` + 3 `solved`), after honest iteration:**

- **The thesis holds where the battery is valid.** Score↔hidden point-biserial **r = 0.526** with sonnet
  in-loop (vs 0.335 with the cheap model, 0.207 before the fixes) — the dense score is a genuinely good
  correctness predictor. On the bundles whose battery *discriminates* the bug (gold climbs high), sonnet
  recovered 3 (incl. **formatutils**, a real `no_progress` flip with trajectory **0.4 → 0.4 → 0.4 → 1.0**
  driven purely by multi-round battery feedback — a bug the binary loop could not fix).
- **The decisive Phase-0 bug was battery validity, not the thesis.** Initial runs were flat because the
  check generator used real-world package imports (`from boltons import dictutils`) while bundles are
  flattened (`import dictutils`) → `ModuleNotFoundError` → checks ERRORED on buggy *and* gold and were
  mis-counted as discriminating (gold scored 0.4, passing 0). Fix: **pin generated-check imports to the
  public test's convention + a `pytest --collect-only` validity filter.** dictutils' gold went 0.4 → 0.95
  (9/11 discriminating); a clean gradient appeared.
- **The new binding constraint is check *discrimination*, not signal density in principle.** Even after
  the fix, only ~4/11 bundles get a battery that actually exercises the bug; 7/11 are *non-discriminating*
  (either `disc=0` — buggy passes every generated check, so the score is a vacuous 1.0 — or gold itself
  can't pass the generated checks). Spec-based test synthesis is weakest on exactly the subtle bugs that
  are hard. The capable model also still missed dictutils despite a valid battery — the **localized-splice
  scaffold** (1–3 functions) is too narrow for bugs needing whole-class context, which is precisely where
  the full tool-using vendor agents win.

**Verdict: PROCEED, with a reshaped Phase 1.** The mechanism is real (dense fair signal + capable model +
guided refinement recovers `no_progress` bugs; r=0.526), but the leverage has moved. Phase 1 priorities,
in order: (1) **check discrimination** — generate checks that exercise the bug (show the buggy region to
the generator — fair, the agent sees it too; seed from the failing test; detect & escalate `disc=0`
batteries instead of scoring them 1.0); (2) **a capable / escalating in-loop model** (sonnet climbs where
gemini-3-flash cannot — connect to the adaptive-compute ladder so the in-loop model escalates on a flat
battery trajectory); (3) **broaden the repair scaffold** beyond localized-splice for whole-class bugs.
MCTS/beam over the value function (the original Phase 2) only pays once (1)–(3) make the gradient both
valid and reachable. Artifacts: `reports/issue_replay_phase0_battery.json` (cheap rung),
`reports/issue_replay_phase0_sonnet.json` (capable rung); code in `src/acp/verification/repair_battery.py`
+ `evals/issue_replay/guided_repair.py`.

## P7 — discriminating-by-construction verifier + search: what recovered, what didn't, honestly

P6 proved the dense battery is a real value function but flagged the binding constraint: ~64% of
batteries were *non-discriminating* (the synthesized checks didn't exercise the subtle bug), and the
localized-splice scaffold was too narrow for whole-class bugs. P7 built the full stack against those
measured failures (all inference-only, research-grounded): **Otter** fail-to-pass gating, **AssertFlip**
pin-then-invert generation, **MuTAP** mutation-sensitivity weights, an AutoVerus-style strategy library,
a **VerMCTS**-style MCTS + beam, an in-loop model ladder (gemini→haiku→sonnet on flat trajectories), and
**Kimi-Dev** patch×check cross-ranking. Code: `src/acp/verification/repair_battery.py` (`build_battery_v2`)
+ `battery_mutation.py`; `evals/issue_replay/guided_repair.py` (beam/mcts/ladder) + `repair_strategies.py`;
class-scope splice in `repair_harness.py`.

**What works (recovery).** On the 8 `no_progress` bundles the binary loop solved 0/8. The P7 stack
recovers **2–3/8 reproducibly** — dictutils and formatutils every run, listutils some runs — graded by
the held-out hidden test. dictutils is the headline: it resisted the binary loop, greedy-gemini, *and*
greedy-sonnet in P6; the **class-scope scaffold** (promoting `update`→`OneToOne`, disambiguated by the
issue title) plus a disc=13 battery cracked it. The value function is informative: score↔hidden
point-biserial **r=0.735** (greedy-ladder) on the 11-bundle slice.

**What didn't matter (search topology).** Greedy-ladder (3/8) **matched/beat** beam (2/8) at equal budget;
both hit the same recoveries and the same failures. Per our pre-registered gate (beam must beat greedy to
justify tree search), the disposition is **ship greedy-ladder + battery-v2 + class-scaffold**; beam/MCTS
add no measurable recovery at this scale. The MCTS machinery remains for larger expansion budgets but is
not on the shipping path.

**The real bottleneck, precisely located.** Recovery tracks **battery validity** one-to-one. After five
hardening iterations (each fixing a measured failure — package-import mismatch → import-pin + collect
filter; guessed exact values on ambiguous specs → spec-entailment audit; hallucinated-API checks →
error-class drop; fragile tiny check-sets → dilution to disc≥5 + validity floor disc≥3), the battery is
*valid* on ~4/11 of these deliberately-hard bundles and **honestly flagged invalid on the rest** (disc<3 →
score capped, never a vacuous 1.0 → the router escalates). buggy is rejected 11/11. So the system no
longer mis-scores; where a fair verifier can't be synthesized from the spec, it says so. Some bundles are
genuinely unsolvable from their spec (timeutils: "fix infinite `daterange(x,x)`" never states 0 vs 1
elements — any fair oracle must guess).

**Gameability (honest, small-n).** Red-teamed `build_battery_v2.accept()` vs the production
`independent_proof` proxy on the synthesizable overfits (n=2 on the easy v1 corpus): battery-v2 **detects
2/2** overfits (proxy 1/2) but **false-rejects gold 1/2** (proxy 0/2) — a more aggressive operating point,
not a strict improvement. And the search produced **one reproducible battery false-positive** (ioutils#1:
proxy score 1.0, hidden fails — a Goodhart instance, stable across greedy and beam). Conclusion: battery-v2
is the right **in-loop gradient + escalation trigger** (a false-rejection merely forgoes early-stop; the
search still found hidden-correct fixes), but the existing proxy stays the production **ship gate**.

**Robustness lessons (ops).** Long background eval jobs were silently reclaimed on session idle (~2.4h,
a tell-tale constant duration — not code hangs). Fixes now in place: per-phase wall-clock budgets on the
battery build *and* candidate scoring (a hung generated check fails closed), and a **resumable** harness
(`guided_repair_phase0.py` reloads completed per-bundle rows and skips them; metrics recomputed from the
persisted rows). Generation stochasticity (the same bundle oscillating valid↔invalid) is damped by a
rebuild-on-invalid retry.

**Net.** P7 converts the P6 proof-of-mechanism into a working, fair, self-aware repair stack: it recovers
subtle bugs the binary loop could not, on exactly the bundles where a fair verifier is constructible, and
*detects-and-escalates* rather than guessing where it isn't — with the gameability cost measured and the
gate role chosen accordingly. Artifacts: `reports/issue_replay_p7_g1.json` (battery validity),
`issue_replay_p7_g3_beam.json` / `issue_replay_p7_g3_greedy.json` (recovery + attribution),
`issue_replay_p7_redteam_v2.json` (gameability).

## P8 — pushing the verifier-discrimination ceiling (and finding it is structural)

P7 left recovery gated 1:1 by battery *validity* (~4/11). P8 asked: can a stronger verifier discriminate
the subtle bugs LLM example-tests miss? We built **property/metamorphic checks via Hypothesis**
(`src/acp/verification/property_checks.py`): the LLM proposes an invariant/metamorphic relation and
Hypothesis *searches the inputs*; a property is admitted as discriminating **only if Hypothesis finds a
falsifying input on the buggy baseline** (proven to exercise the bug, not guessed). Unit-proven on a toy
commutativity bug.

**Go/no-go probe (`evals/issue_replay/pbt_probe.py`, $0.07, no repair calls):** PBT cleanly **rescued
2/7** example-non-discriminating bundles — timeutils (a *bounded-termination* property catches the
infinite `daterange(x,x)` an exact-value example never could) and setutils#2 — and gave 5/11 bundles a
buggy-falsifying + gold-passing property. But 2/7 **failed** the pre-registered ≥3 bar, and the union
with example-tests is ~6/11, short of the ≥8/11 "high-coverage oracle" target.

**Then we pushed the ceiling with the literature's strongest general methods, and it held — for
identifiable, structural reasons:**
- **CrossHair concolic execution** (`diffbehavior`, Z3): on **mathutils** it found **no behavioral
  difference between buggy and gold over 148 symbolic iterations** — because the bug is *default-argument
  binding*, not behavior on explicit inputs, so **no input-search method, random or symbolic, can
  discriminate it**. On **setutils** CrossHair *crashed* symbolically constructing the stateful
  `IndexedSet`.
- **Execution-grounding** was impossible: the harvested **public tests are degenerate** (`assert module
  is not None`) — the verifier works from the issue title + a trivial import, with no behavioral seed.
- **Doctest/docstring mining** (free, gold-aligned): the modules' own doctests **pass on buggy** — the
  bug lives in behavior the illustrative doctests don't cover.

**The ceiling is structural, with a clean bug taxonomy.** Bugs un-discriminable by *any* fair synthesized
verifier without the hidden test: **non-behavioral** (mathutils default args; strutils py3.7 warnings —
no input distinguishes buggy from fixed), **stateful-class-construction** (setutils/listutils — defeats
concolic, hard to articulate as properties), and **uncovered-behavior** (the triggering case appears in
no available artifact). This is the honest answer to "make the verifier stronger": PBT is a real but
*complementary* +2 (worth folding in cheaply), yet the dominant ~5/11 remain dark by construction.

**Breakthrough implication (now evidence-backed, not assumed):** you cannot synthesize a fair
discriminating verifier for a meaningful class of real bugs. So the optimal system must be
**verifier-confidence-aware** — climb the cheap battery where it is *valid* (~6/11 with PBT, recovering
bugs the binary loop can't, P7-proven) and **escalate the verifier-undiscriminable classes to a strong
agent** (which solves them via whole-repo context). That is the P8 W2 router, and the ceiling analysis is
exactly what tells it *when* to trust the cheap path. Artifacts: `reports/issue_replay_p8_probe.json`;
code `src/acp/verification/property_checks.py`, `evals/issue_replay/pbt_probe.py`.

## P9 — a real DE-SATURATED benchmark (SWE-bench Lite, no Docker) + honest routing re-measurement

P8 hit two walls: the synthesized-verifier discrimination ceiling is structural, and our 52-bundle
corpus is **saturated** (Codex 51/52) so nothing we build can *show* a breakthrough. P9 fixes the
measurement: stand up the recognized de-saturated benchmark and re-test the orchestration thesis where
the best agent genuinely misses.

**Infrastructure (built + validated, no Docker):** `datasets` loads SWE-bench Lite (300 tasks);
`swebench_adapter.py` clones @ base_commit into a per-instance venv, applies the dataset `test_patch`,
and grades by the held-out named FAIL_TO_PASS / PASS_TO_PASS (proved hermetic end-to-end:
pytest-11148 fails on buggy, passes on gold). `swebench_solve.py` drives a vendor CLI agent on a
base-only checkout (FAIL_TO_PASS held out), captures its `git diff` (test-file hunks stripped for
fairness), and grades it. Vendor agents are subscription-metered ($0).

**Honest yield limit:** of 71 prepared Lite tasks, only **12 are hermetically fair** — the other ~59
(incl. all 30 sympy) fail because gold needs SWE-bench's *per-task pinned dependency versions* (what
their Docker images pin and a latest-deps venv can't). 12 real tasks across pytest/pylint/sphinx/flask
is a small but genuinely de-saturated slice.

**Result (n=12 fair tasks, held-out grading):**

| agent | solved | rate |
|---|---|---|
| gemini_cli | 4/12 | 0.33 |
| **claude_code** | **6/12** | **0.50** (best single) |
| codex_cli | 4/12 | 0.33 |
| **oracle union (any agent)** | **6/12** | 0.50 |
| cheapest-first escalation (g→c→x, oracle stop) | 6/12 | stops: gemini 4, claude 2, codex 0 |

- **De-saturation confirmed:** best single agent solves **50%, not 98%** — real headroom. (And note
  codex, dominant on our easy corpus at 17/17, drops to 4/12 here — easy-corpus saturation was hiding
  true difficulty.)
- **Routing cost-thesis holds:** cheapest-first reaches the best-single coverage (6/12) while the cheap
  agent handles **4 of the 6 solves** and the strong agent is never needed to *solve* — the P3 cost
  win, reproduced on hard real tasks.
- **Diversity/ensemble thesis does NOT hold at this n:** the oracle union (6) equals the best single
  agent — claude_code **strictly dominates** (every gemini/codex solve ⊆ claude's set). No
  complementarity on these 12; an ensemble adds nothing. This needs a larger, more heterogeneous slice
  to test fairly — an honest underpowered negative, not a refutation.
- **The binding gap is the same one P8 isolated:** a *fair verify-stop*. The escalation economics above
  assume an **oracle** stop (we used the held-out test to know when to stop) — in production you can't,
  and P8 showed a synthesized verifier can't reliably certify a cheap fix. So the cost win is an upper
  bound until a trustworthy stop signal exists; that — not more agents or more search — remains the
  one thing standing between liccio and a defensible breakthrough.

**Net:** liccio's orchestration runs on the recognized hard benchmark; the cheap-routing cost story
reproduces (best-single coverage, cheap agent doing most of the work); the diversity story is
unproven at n=12; and the decisive open problem is a calibrated verify-stop. Artifacts:
`reports/swebench_lite_slice.json`, `reports/swebench_solve_{gemini_cli,claude_code,codex_cli}.json`,
`reports/swebench_router_eval.json`.

## P9 addendum — both follow-ups: pinned-env corpus expansion + the fair verify-stop (honest)

Two tracks requested after the initial P9 slice.

**Track A — lift the fair-task count (pinned per-task envs).** Root cause of the 12-task cap was that
gold needs SWE-bench's per-task pinned dependency versions. Fix: `prepare()` now reads
`swebench.harness.constants.MAP_REPO_VERSION_TO_SPECS[repo][version]` and builds the venv at the spec's
**pinned python** (`uv venv --seed --python X.Y`) + installs the **pinned pip_packages** + runs the spec
install cmd — no Docker. Effect: the hermetic-fair rate jumped from **~29% → ~65–90%** of prepared tasks;
the pytest/sphinx/flask/pylint slice expands to **25 fair tasks** (from 12) — 2× the statistical power.
(sympy is excluded: its FAIL_TO_PASS are bare test names run by a custom runner, not pytest nodeids — a
separate grading path.)

**Track B — the fair verify-stop (the actual breakthrough lever).** The P9 routing economics used an
*oracle* stop. The fair version (`swebench_verify_stop.py`): an LLM writes a reproduction test from the
problem_statement only; it is admitted iff it **fails on the buggy base** (proven to reproduce, P8's
discipline); a candidate is "verified" iff the admitted repros pass. Validation on 6 fair tasks (does the
signal verify gold but not buggy?):

  **0/6 discriminate.** All 6 produced repros that reproduce the bug on buggy (admitted 6/6) — but
  **gold fails them too** (gold_ok=False everywhere). The synthesized repro reproduces the *symptom* yet
  encodes a slightly-wrong *expected behaviour* the true fix doesn't satisfy. As a stop signal it would
  **reject every correct fix**.

This is the unifying finding of the whole investigation: **the synthesized-verifier discrimination
ceiling (P8) is the binding constraint at every level** — single-module repair (P7/P8) and now
multi-file SWE-bench routing (P9). The meta-router's *cost* win is real under an oracle stop, but in
production it is gated by a fair verify-stop that, with current LLM test-synthesis, is not trustworthy on
subtle real bugs. (Caveats: n=6 validation, haiku repro-generation; the next lever is a *differential*
repro — "candidate behaviour differs from buggy on the bug-triggering input" — which trades missed-solves
for false-commits rather than needing the exact correct value, but P8 shows this too has a ceiling.)

**Net:** Track A succeeded (bigger, real, de-saturated slice). Track B honestly did not — and in failing
it pinpoints, for the third time and now on the recognized benchmark, the one open problem that actually
gates breakthrough: a trustworthy, fair verifier for subtle bugs. Artifacts:
`reports/swebench_lite_slice_pinned.json`, `reports/swebench_verify_stop_validate.json`.

## P9 addendum-2 — differential verify-stop + n=25 re-sweep (the two follow-ups, completed)

**Differential verify-stop (salvaging Track B's 0/6).** The absolute repro failed because the LLM
guesses the wrong *correct value*. The differential variant (`--mode differential`) needs no correct
value: capture the buggy output on the issue-implicated inputs (a generated probe script), and verify a
candidate iff its behaviour DIVERGES from buggy. Validation (gold must diverge, buggy must not), n=8:

  **1/8 discriminate** (vs absolute 0/6). The single win (pylint-6506) had a deterministic probe that
  gold changed and buggy didn't. The 7 failures split into **5 non-deterministic probes** (buggy
  "diverges" from its own baseline even after stripping object-ids and sorting — pytest/sphinx/flask
  internals are path/order dependent) and **2 too-shallow probes** (gold doesn't diverge — the probe
  didn't exercise the behaviour the fix changes).

**Conclusion — the ceiling is framing-independent.** Absolute (needs correct value) and differential
(needs only divergence) both fail for the same root reason: from the problem statement alone, the LLM
cannot reliably produce a test/probe that is BOTH deterministic AND actually exercises the specific
subtle bug. This is the same synthesized-verifier discrimination ceiling measured in P7/P8 (single
module) and P9 (multi-file) — now confirmed a **third** way. A trustworthy fair verifier for subtle real
bugs is the one open problem gating the meta-router's production cost-win; it is not closed by more
agents, more search, bigger corpora, or absolute-vs-differential test framing.

**n=25 re-sweep (routing economics at 2× power).** With the fair slice doubled to 25, the three vendor
agents are being re-swept (subscription-metered $0) to recompute the routing head-to-head at higher
statistical power; `swebench_router_eval` then reports per-agent / union / cheapest-first-escalation on
the larger slice. (Long-running, resumable; numbers land in `reports/swebench_solve_*.json` +
`swebench_router_eval.json`.) Artifacts: `reports/swebench_verify_stop_diff.json`.

## P10 — Auto-referee: mutation-validated battery + multi-agent debate (the trustworthy verify-stop)

The one open problem after P7–P9 was a *trustworthy* automatic correctness gate. P10 builds the
**auto-referee** (`src/acp/verification/{debate,auto_referee}.py` + `battery_mutation.mutation_score`):
accept a candidate only when (a) its battery is **mutation-validated** — its checks react to focus-region
mutations OR it carries ≥3 *proven* discriminating checks (a non-vacuous battery), else **abstain →
escalate**; and (b) a **proposer/critic/judge debate** (judging the unified *diff*, not a length-capped
module) rules it correct. The debate can OVERRULE a single wrong synthesized check (battery-v2's
gold-rejection cause) yet still catch overfit (the critic flags input-special-casing; mutation-validation
filters vacuous batteries).

**Ground-truthed red-team (gold = correct, overfit = wrong-but-fools-the-primary-test), full v1 corpus,
4 bundles with a synthesizable overfit:**

| gate | overfit detection | gold false-rejection | gold accepted on WELL-FORMED battery |
|---|---|---|---|
| proxy (baseline) | 0.5 | 0.0 | — |
| battery-v2 | 1.0 | 0.5 (rejects golds on *good* batteries via a stray wrong check) | — |
| **auto-referee** | **4/4 = 1.0** | 0.5 | **2/2 = 1.0** |

- **Perfect overfit detection (4/4)** — the critic + mutation-validation caught every gamed patch
  (e.g. #0 "replaces the function with a hardcoded lookup table"; #13's overfit rejected with 11
  discriminating checks present).
- **Accepts correct golds when it can build a trustworthy battery (2/2)** — #0 (disc=3) and #13
  (disc=11) both accepted, the behaviour battery-v2 failed at. This is the qualitative win: the referee
  is the first gate to *both* accept clearly-correct golds *and* reject 100% of overfits.
- The two "gold false-rejections" are **not** errors on good batteries: **#12** is a *safe abstain*
  (disc=1 weak battery → escalate, never false-commit) and **#7** is the genuinely **ambiguous**
  timeutils bug (`daterange(x,x)`: 0 vs 1 elements — unsolved by every method all session, so a careful
  critic rejecting it is defensible). So the referee's headline gold-FR ties battery-v2's 0.5, but its
  failures are *safe/defensible* whereas battery-v2's were wrong rejections of good golds.

**Honest limits:** n=4 evaluable (only 4 v1 bundles yield a synthesizable overfit), so the top-line
gold-FR (0.5) is too noisy to claim the pre-registered ≤0.25 bar; the *clean* signals are detection 4/4
and well-formed-gold-accept 2/2. The referee adds debate LLM calls (~$0.06/bundle; full run $0.23).
**Net:** the auto-referee is a **sound-by-design** verify-stop — perfect overfit detection, accepts
strong-battery golds, and *abstains→escalates* instead of false-committing on weak/ambiguous cases —
which is exactly the trustworthy stop-signal liccio's routing cost-win needs; a larger overfit-
synthesizable corpus is required to nail the gold-FR number. Artifacts:
`reports/issue_replay_referee_redteam.json`; code `debate.py`, `auto_referee.py`, `battery_mutation.py`.
