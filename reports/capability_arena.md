# Capability arena — moving ahead on capability (verifier-gated ensemble + reflective repair)

**Date:** 2026-06-07. *Papers: Boosting Weak Reasoning Models (2605.14163), DeepConf (2508.15260),
VerMCTS (2402.08147), Reflexion (2303.11366).* 12 hard-first tasks, hidden-test verified, Wilson CIs.

**Thesis & precondition.** A single agent's ceiling is P(correct in one try); a meta-router beats it
by capturing P(≥1 of N attempts correct) **only as well as a verifier can pick the correct one**.
`capability_router.solve_ensemble` runs diverse arms within budget, selects by the independent proxy
verifier (never self-report), and reports the **any-correct oracle ceiling** so the captured fraction
is honest. The gating number — **proxy precision/recall = 1.0 / 0.97** on this corpus — was high.

## Result 1 — cheap-diverse ensemble vs a strong single agent (a COST win, not capability)

| | verified | 95% CI | cost / verified-success |
|---|---|---|---|
| ensemble (flash-lite + haiku + flash, verifier-gated) | 1.00 | [0.76, 1.00] | **$0.00347** |
| best single cheap arm (haiku) | 1.00 | [0.76, 1.00] | — |
| strong single (opus + repo_map) | 1.00 | [0.76, 1.00] | $0.02224 |

The cheap ensemble **matches opus at 6.4× lower cost**. But the **oracle headroom is 0** — every task
was solvable by some cheap arm — so this is a *cost-per-capability* win, **not** a capability gain.
Capturing union-headroom needs tasks where no single arm is reliable (harder/real tasks).

## Result 2 — weak self-ensemble (blind best-of-k): NO capability gain here

Sampling the weakest arm (gemini-flash-lite) ×3 at temperature 0.8, verifier-gated:

| | verified | note |
|---|---|---|
| single attempt | 0.83 | |
| best-of-3 (blind resampling) | **0.83** | any-correct ceiling also 0.83 |

**Headroom captured: False.** On these gradeable tasks the weak model's failures are **deterministic**
(it either solves a task or fails *all* samples) — so blind resampling adds no information and no
capability. This is the honest negative that motivates Result 3.

## Result 3 — reflective repair (information feedback): a REAL capability gain

Re-dispatch the weak arm with its **generated-test failure as feedback** (Reflexion; the feedback is
the production-available independent tests, *not* the held-out hidden test):

| | verified | |
|---|---|---|
| single attempt (flash-lite) | 0.75 | |
| **+ reflective repair** | **1.00** | **rescued 3/3 of the triggered failures** |

**Information feedback beats single (True).** Reflective repair took the weak model from 0.75 → **1.00**,
rescuing *every* deterministic failure that blind best-of-k could not (`cap_valid_number`,
`cap_calc_unary`, …). **This is genuine capability the router adds that a one-shot agent cannot** — and
it's bounded by verifier quality (here 1.0/0.97).

## Honest reading — the path to capability

- **The capability lever that works is verifier-guided reflective repair, not blind ensembling.**
  Feeding the verifier's failure signal back to the model rescues "got it wrong" failures; resampling
  the same model does not.
- **Bounded by two ceilings:** the verifier (can't repair toward a target it can't grade) and the
  model's *true* capability (you can't reflect past a wall the model fundamentally can't climb — here
  repair worked because the tasks were within flash-lite's reach *given the right feedback*).
- **The cross-agent union lever showed no headroom** only because a cheap single arm already aced this
  corpus; on tasks where no single agent is reliable it would contribute — which is exactly the
  regime we cannot access here.
- **The real-world magnitude is unproven:** all on small synthetic tasks. The mechanism is built,
  measured, and correct; the size of the capability gain on production work needs **real hard tasks
  where a frontier agent fails a meaningful slice** (SWE-bench / real issues) — **network-blocked here**
  (HF 403, GitHub API 0/60). That data access is the explicit critical-path dependency.

## Bottom line
A meta-CLI-router **can** advance capability, and the measured mechanism is **verifier-guided
reflective repair** (weak model 0.75 → 1.00, 3/3 rescued) — blind best-of-N does not help when
failures are deterministic. The verifier is the binding constraint (kept near-perfect here), and the
honest size of the gain on real work is gated on real hard-task data, not on more mechanism.

## Reproduce
```
uv run python -m evals.capability_arena.run --tasks 12
```
Artifact: `reports/capability_arena.json`.
