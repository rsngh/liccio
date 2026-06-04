# Round 17 — Unified Coordination + A/B-Gated Skill Canaries

A self-directed increment after the closed-loop skills of Round 16: unify the full
coordination surface into one decision, and add **online** statistical validation
(A/B canaries) for skill promotion — beyond the fixed held-out gate.

## Delivered

| # | Title | What shipped |
|---|-------|--------------|
| 1 | Unified coordination | `routing/coordination.compose_coordination` binds model (capability matrix), workflow shape (safety-gated topology policy), and active skill (registry) into one auditable `CoordinationDecision` with per-layer rationale — the full AgensFlow coordination surface. |
| 2 | A/B canary gate | `training/skill_canary.evaluate_ab_canary` — a two-proportion one-sided test of canary vs control **conclusive** solve rate; promotes only on a significant, uncontaminated lift with adequate samples. |
| 3 | Live A/B canary | `evals/scripts/run_skill_canary_live.py` — real control/canary rollouts, measurement-trust classification, statistical gate. |
| 4 | Online-validated deploy | `skill_deploy.canary_then_deploy` — deploy a skill ONLY if the A/B canary promotes; wires the statistical gate into the governed deployment path. |

## Live validation

**A/B canary (weak openai_harness):** control 0.0 vs canary 0.0 over 6 conclusive attempts
per arm (uncontaminated) → lift 0.0, p=0.5, not significant → **promote=False**. An honest
result that validates the gate end to end: two clean arms, conclusive classification, a
two-proportion test, and a correct refusal to promote a skill with no measured lift.
`reports/live/skill_canary.json` (secret-scanned, registered → 45 artifacts).

## Tests (13)

- coordination (3): binds model+topology+skill; security never gets an unsafe skip; no-evidence safe.
- A/B canary (5): clear lift promotes; no-lift / small-sample / min-lift / contaminated block.
- canary_then_deploy (2): significant lift deploys; no-lift blocks.
- (Round 16 deploy/inject/loop tests remain green.)

Cost is a first-class tiebreak; safety is enforced before any cost saving; and no
contaminated measurement can promote a skill — the measurement-trust invariant now also
governs online skill A/B promotion.
