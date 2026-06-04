# Round 18 — Autonomous Skill Self-Improvement Orchestrator + Dashboard

A self-directed increment after the unified coordination + A/B canaries of Round 17:
make skill optimization a **governed, autonomous, auditable cycle** with a durable
evolution timeline surfaced in the operational health snapshot.

## Delivered

| # | Title | What shipped |
|---|-------|--------------|
| 1 | Evolution timeline | `schemas/skill_evolution.SkillEvolutionEvent` + `skill_evolution_events` table (migration `e5f6a7b8c9d0`) — every cycle outcome per scope is durably recorded (deployed / no_op, base/best score, reason, cycle id). |
| 1 | Autonomous cycle | `training/skill_improvement.run_skill_improvement_cycle()`: one governed pass over scope jobs — runs the SkillOpt loop, deploys improvements behind the gate, persists an event for each scope. |
| 1 | Dashboard | `skill_dashboard()` (CLI `acp skill dashboard`): active skills per scope + evolution-by-action + recent timeline. |
| 2 | Health surfacing | `control_plane_health` gains a `skills` section so an operator sees learned + deployed skills next to measurement/routing health. |

## How it ties together

The cycle is the closed loop made continuous and observable: trusted conclusive traces →
SkillOpt loop (held-out gate) → governed deploy (canary/rollback) → recorded event →
dashboard / health. Nothing deploys without a measured, uncontaminated gain; everything is
versioned, attributable, and reversible.

## Tests

- cycle + dashboard (1): a 2-scope cycle deploys the improving scope, no-ops the flat one,
  records both events, and the dashboard reflects 1 active skill + the timeline.
- health (1): the `skills` section is present in the snapshot.
- migration down/up cycle verified.

All gates green; counts synced; pushed to `feat/agent-control-plane`.
