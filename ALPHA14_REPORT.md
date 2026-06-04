# Alpha 14 / Round 14 — Production-Gated, Measurement-Trustworthy Routing Platform

**Mission:** turn ACP into a **production-gated, measurement-trustworthy routing
platform** — one that classifies measurement failures, enforces provider/sandbox
policy, persists only trustworthy evidence into learning systems, explains every
routing decision, and blocks production mode when evidence is stale or contaminated.

This round makes the measurement-trust contract a *hard invariant* (proven by a single
end-to-end test), adds per-dimension measurement-quality scoring with a matrix floor,
formalizes provider-policy enforcement with auditable call records, and ships a fully
learned (but safety-gated) topology policy.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1 | Release sync | ALPHA13_CHECKLIST + CURRENT_STATUS Round 13 paragraph; docs-consistency green. |
| 2 | **AttemptOutcome hard invariant** | `assert_quality_eligible` + `ContaminatedSampleError`; the headline test proves a contaminated attempt changes neither matrix solve-rate nor OPE quality reward. |
| 3 | MeasurementQuality v2 | Per-dimension `DimensionVerdict` + `MeasurementQualityViolation` + per-dimension floor map; breakdown visible in the policy dossier. |
| 4 | CapabilityMatrix hardening | `best_for` withholds a recommendation below `MIN_MEASUREMENT_QUALITY` (noisy run). |
| 5 | Cost-aware OPE v3 hardening | `policy_value_under_profile` / `is_policy_promotable_under_profile` — a high-success-but-contaminated or costly policy is blocked under the relevant profile. |
| 6 | Provider policy enforcement | `ProviderPolicyRegistry` (refuses unsafe policy) + `ProviderCallRecord` + `detect_violations` (retry/timeout violations observable). |
| 12 | Broader live corpus | 8 task types (added migration + docs); **103 conclusive live cells** persisted. |
| 13 | Measurement mutation suite v3 | None update solve-rate or policy promotion — proven across classifier/hygiene/quality/availability. |
| 16 | Fully learned topology | `recommend_topology` picks the cheapest SAFE arm holding success; `should_update_topology_policy` refuses contaminated runs. |

(WS7/8/9/10/11/17/18 were delivered in Rounds 12–13 and remain green.)

## Live validation (real OpenAI + Anthropic harnesses)

A 4-rep no-patch bakeoff over the 8-task-type corpus (208 attempts, 1 infra hang excluded):

- **103 conclusive cells** persisted to a DB across all 8 task types.
- `measurement_quality.json` — overall **0.9964**, trusted=true.
- hygiene solve_rate **0.9515**, not contaminated; availability not degraded.
- Production health gates `measurement_quality_trusted` + `harness_availability_ok` true on
  the real artifacts.

## Gate

```
uv run pytest -q --timeout=300   # full suite green
uv run ruff check .              # clean
uv run mypy src                  # clean, 225 source files
uv run alembic upgrade head      # OK
uv run acp reports validate      # 42 artifacts valid
```

## Honest status / remaining

Delivered: WS1–6, 12, 13, 16 (this round) on top of the Rounds 12–13 stack. Remaining
(environment-gated): WS14 (Docker live-security gate — needs a running Docker daemon and a
committed fresh artifact), WS15 (vendor live campaign — needs codex/SDK binaries), WS19
(local LoRA pilot — needs a GPU). These are honestly labeled, not claimed.
