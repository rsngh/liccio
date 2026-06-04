# Alpha 15 / Round 15 — Self-Optimizing Skill-and-Routing Platform (SkillOpt)

**Mission:** turn ACP from a measurement-trustworthy routing platform into a
**self-optimizing skill-and-routing platform** — one that safely optimizes compact
procedural skills from *trusted conclusive traces*, validates them on held-out tasks,
rejects negative transfer, and routes with skill-aware capability evidence.

This round integrates **SkillOpt** (the Microsoft library, `pip install skillopt`) behind
ACP governance: a skill is external state for a FROZEN agent, edited in bounded steps and
accepted only when it improves a held-out validation score — never a silent prompt mutation.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1 | Release truth | ALPHA14_CHECKLIST; counts synced (853/42/225). |
| 2 | Skill registry | `SkillDocument` + `SkillScope` (versioned, hashed, scope-bound) + `skill_documents` table + `acp skill list/show/diff`. |
| 3 | SkillOpt backend | `MicrosoftSkillOptBackend` (real `skillopt.evaluate_gate`) + `ACPInternalSkillOptBackend` (always-available) + `get_backend()` fallback + `acp skill optimize --dry-run`. |
| 4 | Trusted dataset builder | `build_skill_dataset` — conclusive-only (contaminated excluded via the learning gate), deterministic train/held-out split. |
| 5 | Edit engine + loop | `apply_edits` (bounded append/insert_after/replace/delete, secret-redacted) + `optimize_skill` (propose → apply → score on held-out → gate → keep best; deployable only on strict held-out improvement). |
| F | Contamination gate | contaminated/provider attempts excluded from train AND held-out. |
| G | Negative-transfer gate | a held-out-flat or held-out-regressing edit is rejected; baseline retained. |

## Live validation (real OpenAI rollouts, microsoft_skillopt gate)

**Run 1 (ceiling / no-noise):** held-out tasks the strong harness already solves →
base_score 1.0 → the gate **rejected all candidate skills** (no held-out gain) →
not deployable. The held-out gate's central anti-noise property, working live.

**Run 2 (headroom, weak harness — DEPLOYABLE win):** a budget-constrained harness
(max_steps=3, no nudges) on the harder tasks solved **0.5** of the held-out split. SkillOpt
**accepted** the edit *"After editing, ALWAYS run the project's tests and fix failures
before finishing"* (held-out 0.5 → **1.0**, `accept_new_best`), then **rejected** the two
non-improving follow-up edits — yielding a compact, inspectable, validated **deployable**
skill (next version v2). The same `microsoft_skillopt` gate that made no change at the
ceiling produced a real validated improvement where there was headroom.

## Gate

```
uv run pytest -q --timeout=300   # full suite green
uv run ruff check . && uv run mypy src   # clean (231 src)
uv run alembic upgrade head      # OK
uv run acp reports validate      # artifacts valid (incl. skillopt_run.json)
```

## Honest status / remaining

Delivered the SkillOpt core (WS1-5, F, G) + live validation. `skillopt` is treated as an
OPTIONAL dependency (try_import) so the gate stays green without it; the internal backend
has identical gate semantics for CI. Remaining (environment-gated, carried from prior
rounds): Docker live-security gate, vendor live campaign, local LoRA pilot.
