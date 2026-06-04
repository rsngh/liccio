# Round 19 — Safe End-to-End Live Autonomous Self-Improvement

The capstone of the self-optimizing arc: run the full governed loop **live, end to end**,
with safety guardrails — and prove it deploys nothing without a measured, governed gain.

## Delivered

| # | Title | What shipped |
|---|-------|--------------|
| 1 | Cycle guardrails | `CycleGuardrails` on `run_skill_improvement_cycle`: `abort_on_contaminated` skips a scope whose evidence is contaminated (a noisy run never drives a deploy); `max_deploys` caps the per-cycle blast radius. Reported as `n_skipped_contaminated` / `n_skipped_cap`. |
| 2 | Live autonomous run | `evals/scripts/run_autonomous_cycle_live.py` — a per-scope job with a LIVE held-out scorer → guardrailed cycle → governed deploy → persisted event → dashboard, all against a real (weakened) openai_harness. |

## Live validation

The autonomous cycle ran live against the weak openai_harness: the live held-out scorer
rolled out tasks (this split scored **0.0** baseline), the SkillOpt gate found no
improvement, and the cycle correctly recorded a **`no_op`** — **0 skills deployed**, with
the reason and an audit event. The capstone safety property holds end to end: **the
autonomous loop deploys nothing without a measured, governed gain.** (A deployable lift was
shown standalone in Round 15: 0.5 → 1.0.) `reports/live/autonomous_cycle.json`
(secret-scanned, registered → 46 artifacts).

## The complete self-optimizing loop (Rounds 15-19)

```
trusted conclusive traces (measurement-trust gate)
  -> trusted SkillOpt dataset (contaminated excluded)
  -> bounded-edit optimization (held-out validation gate)
  -> governed deployment (canary/A-B + rollback)
  -> active-skill injection at routing time
  -> skill-aware capability evidence
  -> autonomous cycle (guardrailed) + evolution timeline + dashboard + health
```

Every stage is gated on measured, uncontaminated improvement; everything is versioned,
attributable, reversible, and observable. Nothing self-edits into noise.

## Tests

- guardrails (3 added): contaminated scope skipped; deploy cap stops after N.
- (all Round 15-18 skill tests remain green.)

All gates green; pushed to `feat/agent-control-plane`.
