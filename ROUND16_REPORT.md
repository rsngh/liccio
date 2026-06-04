# Round 16 — Closed-Loop Skill Deployment + Skill-Aware Routing

A self-directed increment (after the SkillOpt integration of Round 15): take learned
skills from "optimized" to **deployed, in-force, and attributed** — a closed loop, fully
governed, with a cross-harness transfer experiment.

## Delivered

| # | Title | What shipped |
|---|-------|--------------|
| 1 | Governed deployment | `skill_deploy.deploy_skill` promotes a candidate to ACTIVE only if its canary strictly beats the active baseline, archiving the prior version as the rollback target; `rollback_skill` restores it. |
| 2 | Skill-aware injection | `skill_inject.inject_active_skill` prepends the ACTIVE skill for a routing scope into the agent context, so a deployed skill takes effect at routing time. |
| 3 | Skill-aware matrix | Capability cells carry `skill_id` / `skill_version` attribution — routing evidence is bound to the skill version in effect. |
| 4 | Closed-loop orchestration | `skill_loop.optimize_and_deploy`: trusted dataset → governed SkillOpt loop → deploy behind the canary/rollback gate, all auditable. |
| 5 | Cross-harness transfer | Live experiment measuring whether an openai-optimized skill transfers to claude. |

## Live validation

**Cross-harness transfer (openai → claude):** the compact skill *"After editing, ALWAYS
run the project's tests and fix failures before finishing"* (which lifted a weak
openai_harness 0.5 → 1.0 on held-out in Round 15) was injected into a weakened
claude_harness: baseline **0.333**, with-skill **0.333**, **gain 0.0, transferred=False**.

An honest null result — and a clean governance demonstration: ACP *measures* transfer and
would **refuse to deploy** a non-improving skill to the target (the validation/deploy gate
rejects a zero gain). The same machinery that deployed a real improvement on openai
correctly deploys nothing on claude where there is no measured benefit.

## Tests

- deploy/rollback (3): block without canary gain; archive prior + activate; rollback restores.
- injection (3): none unchanged; active skill prepended; no-match returns original.
- skill-aware matrix (2): attribution populated / None.
- closed loop (2): optimize→deploy→inject end to end; no-improvement deploys nothing.

`reports/live/skill_transfer.json` committed (secret-scanned, registered). All gates green.
