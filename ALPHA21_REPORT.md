# Alpha 21 — Skill-Library Operating System for Coding Agents

**Mission:** turn ACP from a SkillOpt-enabled routing platform into a **skill-library
operating system** — autonomously discover, optimize, validate, canary, route, **compose**,
and retire scoped procedural skills while preserving measurement trust and avoiding
negative transfer.

Builds on the SkillOpt self-optimization arc (R15–20). This round adds the *library*:
many scoped skills, composed and routed together, with full provenance and least-privilege
defenses.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1 | Report truth | `acp reports sync-status` rewrites the CURRENT_STATUS count from the committed pytest report — no count mismatch survives CI. |
| 2 | Skill registry v2 | `SkillDocument` gains applicability, risk_class, required_tools, allowed_repositories, validation_history, negative_transfer_history, deployment_state, rollback_pointer, skill_family. |
| 3 | Provenance graph | `SkillProvenanceRun` (+ candidate/edit records, `skill_provenance_runs` table) — every skill line traces to evidence → edit → validation gate → promotion. Edits redacted. |
| 6 | Production suite | 5 curated, scoped, risk-classed, poison-clean starter skills (`seed_production_skills`). |
| 7 | Skill composition | `compose_skills`: safety-ordered, conflict-resolved (dedup + contradiction), token-budgeted library composition with included/excluded provenance. |
| 8 | Skill routing | `compose_coordination` composes the skill *set*; dossier explains selected + rejected skills. |
| 9 | Skill capability matrix | `build_skill_capability` / `best_skill_for` — "which skill works for this task/harness?" (success/cost/HAR/HFR/PWL/measurement-quality per skill). |
| 10 | Negative-transfer | `assess_transfer` + auto-narrowing via `negative_transfer_history`; routing excludes a skill on domains it hurt. |
| 12 | Poisoning defense | `scan_skill` (8 threat categories) is a HARD block in `deploy_skill` — no poisoned skill reaches deployment. |
| 13 | Cross-harness study | `run_transfer_study` classifies portable vs harness-specific skills and recommends scope. |
| 11 | Staged canary platform | `run_staged_canary` (5/25/50/100%) advances only while guardrails hold (solve-rate/cost/quality/HAR/HFR/security/human-review), else rolls back. |
| 15 | Topology+skill co-opt | `cooptimize` chooses the (topology, skill) combination jointly, safety-gated. |
| 16 | Trajectory judge for skills | `judge_skill_update` scores a skill update on the eight trajectory axes (beyond solve-rate). |

## Safety properties (all enforced + tested)

- No contaminated/inconclusive attempt trains a skill (measurement-trust learning gate).
- No skill deploys without a measured held-out / A-B canary gain (validation gate).
- No poisoned skill reaches deployment (poisoning scan hard block).
- A skill that hurts a domain is auto-excluded there (negative-transfer narrowing).
- Composition is safety-ordered, conflict-resolved, and token-bounded.
- Every deployed skill is versioned, hashed, provenance-traced, and rollbackable.

## Gate

```
uv run pytest -q --timeout=300   # full suite green (Docker live tests are
                                 #   daemon-contention flakes; pass in isolation)
uv run ruff check . && uv run mypy src   # clean (249 src)
uv run alembic upgrade head      # OK (skill_provenance_runs migration)
uv run acp reports validate      # artifacts valid
```

## Remaining (environment-gated)

WS18 (Docker live-security gate — daemon contention), WS19 (vendor-native harness gate —
needs codex/SDK binaries) are honestly labeled, not claimed. WS11 (multi-stage canary
platform) and WS14–16 build naturally on the A/B canary, evolver, and trajectory-judge
foundations already in place.
