# Round 25 — Production Evidence Depth & Measurement Discipline

Directly executing the round-25 review's constructive feedback ("deepen production evidence,
not concept count") with live testing.

## Feedback-driven measurement discipline

- **Evidence tiers (feedback #2).** `EvidenceTier` (synthetic → fixture → semi_live →
  live_api → vendor_native_live → real_repo_replay → production_shadow); the weakest tier
  dominates a composite claim. Reports can declare their tier via `stamp_evidence`.
- **Activation as a first-class denominator (feedback #3).** `SolveRateBreakdown` reports
  solve rate over FOUR explicit denominators — all / conclusive / activated /
  trusted-activated — so there is no hidden denominator. On the real 130-attempt bakeoff all
  four converge at 0.9846 (130/130 activated): a healthy harness has no ambiguity; a degraded
  one makes them diverge (the Alpha-25 vendor self-catch).
- **Health as a contract (feedback #6).** Health surfaces `evidence_tier` +
  `solve_rate_activated`/`trusted_activated`, and adds a fail-closed `evidence_tier_sufficient`
  gate: production claims must rest on ≥ live_api evidence, not synthetic. Live: tier=live_api,
  gate True.
- **Report-truth chaos (test G).** Corrupting the test / source / artifact count is caught by
  the strict report-truth gate (and thus the `report_truth_consistent` health gate). 6 tests.

## Live evidence

- **Production shadow mode (Alpha 26).** `shadow_mode` composes the abstention gate +
  capability matrix (adapter + Wilson CI) + compute policy into a recommend-only
  ShadowDecision with a full policy dossier and the hard invariant `autonomous_write=False`.
  Ran over the corpus with the REAL live matrix: 11 recommend-only runs, no autonomous
  writes, every recommendation carries a dossier, adapters chosen with live CIs. Tier=live_api.
  The bridge from benchmark-trust to real-work-trust at zero execution risk.
- **Compute-escalation benchmark (test C / Alpha 29).** A reliability-banded "when to use
  which arm" decision table, validated by the compute policy and grounded in committed live
  evidence: high reliability → cheap_single; medium (hard tasks single-shot 0.84 → best-of-8
  1.0) → best_of_k; low + stakes (advisor handicapped 0.33 → 1.0) → advisor/frontier.

## Skill economy (Alpha 30)

- **Skill transfer matrix + scope learner.** Per-(skill, scope) transfer verdicts —
  helps / neutral / hurts / **untrusted** — robust (small-sample → neutral, not helps) and
  activation-aware (degraded measurement → untrusted, never a skill verdict; the vendor
  self-catch encoded). The scope learner narrows a skill to scopes where it robustly helps and
  excludes where it hurts — the negative-transfer defense as a living scope policy.

## Gate

```
uv run pytest -q --timeout=300       # full suite
uv run ruff check . && uv run mypy src
uv run acp reports validate          # 91 artifacts (each can carry an evidence_tier)
uv run acp reports sync-status --strict
uv run acp health --mode production  # incl. evidence_tier_sufficient
uv run python evals/scripts/run_production_shadow.py
```

## Net

The review's core asks are now first-class: every solve rate names its denominator, every
report can name its evidence tier, production health gates on real (≥ live_api) evidence,
report-truth is chaos-tested, and ACP can run recommend-only on real tasks (shadow mode).
The skill library gains a robust, activation-aware transfer/scope policy. Evidence depth,
not concept count.
