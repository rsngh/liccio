# Alpha 25+ — Production Coherence, Evidence Truth & Compute Policy

Driven by the round-24 review. Mission: make ACP impossible to overclaim, treat infra flakes
as measurement data, escape the easy-task ceiling with real evidence, and turn expensive
compute into a ledger-gated policy.

## Production coherence & evidence truth (Alpha 25)

- **Report-truth hard gate.** `release_truth.py` computes canonical counts (source files /
  artifacts / test pass+skip) from authoritative sources; `acp reports sync-status --strict`
  fails closed if `CURRENT_STATUS.md` disagrees. It immediately caught a live 277→279
  source-count drift. The stale header (Round 12, 258 src, 46 artifacts) is fixed to the
  truth (Alpha 25, 279 src, 86 artifacts). New `report_truth_consistent` production gate.
- **Infra-flake taxonomy.** `infra_taxonomy.py` classifies every infrastructure event —
  docker loss before/mid-run, pytest-in-pytest contention, provider timeout/429, vendor CLI
  not-installed/hang — as infra/inconclusive: never a model failure, skill failure, or
  capability update, each with a health signal and an AttemptOutcome mapping.
- **docker-security-live** treats mid-run daemon loss as a clean skip, not a failure.
- Tests A (report truth), B (infra classification), H (production fail-closed).

## Evidence depth — escaping the ceiling (test F)

The review's key critique: easy-task ceiling dominates, so best-of-k/advisor show no uplift.
`hard_tasks.py` adds 5 greedy-trap tasks (coin_change, word_break, lis, max_product,
min_path_sum) where the buggy module uses a plausible GREEDY approach to a DP problem. Proven
offline (greedy fails, DP reference passes). **LIVE (gpt-4o-mini, blind + held-out pytest):**

```
single_shot_rate = 0.84   (coin_change 3/5, max_product 3/5 — genuinely hard)
best_of_8_rate   = 1.0    lift +0.16   ceiling_escaped = True
```

First real evidence that sampling k cheap candidates + an execution verifier buys solve rate
where single-shot is unreliable.

## Compute-escalation policy (Alpha 29)

`compute_policy.py`: pick a compute arm (cheap_single / best_of_k / advisor / frontier) from
measured single-shot reliability + risk/value. `ComputeSpendLedger` records (arm, cost,
solved) and computes marginal value (solve lift per extra dollar over cheap baseline). The
policy escalates to an expensive arm **only where marginal value is positive**. The live
bakeoff confirms the mechanism: on a sample where single-shot already solved every task it
correctly **withheld** escalation and reported best-of-k/advisor marginal value as not
positive — spending compute only where evidence justifies it (paired with `hard_best_of_k`'s
5-rep 0.84 estimate showing where it would escalate).

## Honest synthesis

Alpha 24 found best-of-k withholds on easy tasks (k=1 optimal); Alpha 25 shows it lifts on
genuinely hard tasks (0.84→1.0); Alpha 29 makes the policy spend compute exactly where the
ledger shows positive marginal value. The platform now measures, decides, and reports its own
truth honestly — and can no longer overclaim its status.

## Gate

```
uv run acp reports sync-status --strict   # report-truth hard gate
uv run pytest -q --timeout=300
uv run ruff check . && uv run mypy src
uv run acp reports validate               # 86 artifacts valid
uv run acp health --mode production       # explicit gates incl. report_truth_consistent
```
