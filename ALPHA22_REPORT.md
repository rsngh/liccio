# Alpha 22 — Production-Gated Live Harness & Skill Deployment Platform

**Mission:** turn ACP from a skill-library OS into a **production-gated live harness and
skill deployment platform** — safely run Docker-isolated vendor-native coding harnesses,
inject and evaluate skills, promote them through statistically sound staged canaries, and
**fail closed** when live security, vendor proof, measurement quality, or report truth is
missing.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1 | Release truth | `acp reports sync-status`; ALPHA21_CHECKLIST; counts agree (961/46/258). |
| 3 | Docker contention hardening | unique `acp-run-<uuid>` names + `acp.managed=true` labels + ACP-only prune + transient retry. Docker tests pass repeatedly. |
| 5 | Vendor health detector | `detect_vendor_health()` — codex/claude/openhands {available, version}; unavailable skip. |
| 6 | No-patch smoke fixture | `build_smoke_fixture()` — a real failing-divide repo (verified fail→fix→pass). |
| 7/8 | Codex/Claude native harnesses | `VendorNativeHarness.run_smoke()` captures version/command/cwd/timeout/diff/pytest/secret-scan + AttemptOutcome. |
| 9 | OpenHands native harness | `openhands_capability_level()` — reports actual level (health) without overclaiming. |
| 10 | Vendor skill-injection | SKILL.md injected; `skill_injected` / `skill_used_observed`. |
| 11 | Vendor measurement-trust | `VendorRunResult.to_cell()` classified by the real measurement-trust layer (timeout = infra/inconclusive). |
| 12 | Vendor production gate | `vendor_harness_live_passed` (≥1 native solve) in `acp health --mode production`. |
| 13 | Staged canary persistence | `SkillCanaryRun` + `skill_canary_runs` table — survives process restart. |
| 14 | Canary statistics | Bayesian beta-binomial `bayesian_canary()` + credible intervals + low-N abstain. |
| 15 | Canary → deploy/rollback | `staged_canary_deploy()` — promote at 100% / rollback any stage / advisory + persisted run. |
| 16 | Vendor + SkillOpt live canary | live claude_code baseline-vs-candidate → canary gate. |
| 17 | Skill-aware vendor matrix | `skill_capability_table()` — which skill works with which (vendor) harness. |
| 18 | Cross-harness transfer live | live portability classification under vendor harnesses. |
| 19 | Operator docs/scripts | `docs/{docker_live_security,live_vendor}.md` + `scripts/run_ws18.sh` / `run_ws19.sh`. |

(WS2 = WS18 docker gate, WS4 = WS19 vendor gate, both delivered + live-proven in the prior round.)

## Live validation (real installed vendor tools)

- **WS18/WS19 gates:** `acp eval docker-security-live` → 9/9 pass; `acp eval
  vendor-harness-live` → **codex + claude both solve** the no-patch task, openhands
  health-checked, passed=true. Production gates `docker_live_security_passed` and
  `vendor_harness_live_passed` both **true**.
- **WS16 vendor+skill canary (claude_code):** control 1.0 vs canary 1.0 on the trivial
  fixture → lift 0.0, P(better)=0.5 → **decision=hold** (honest non-promotion; the gate
  refuses to promote without a measured lift). `reports/live/vendor_skill_canary.json`.
- **WS18 cross-harness transfer:** see `reports/live/cross_harness_vendor_transfer.json`.

## Gate

```
uv run pytest -q --timeout=300   # 961 passed, 5 skipped
uv run ruff check . && uv run mypy src   # clean (258 src)
uv run alembic upgrade head      # OK (skill_canary_runs migration)
uv run acp reports validate      # artifacts valid
uv run acp eval docker-security-live && uv run acp eval vendor-harness-live  # pass
```

## Fail-closed posture

Production health now fails when any of these is missing/stale: Docker live-security,
≥1 vendor native solve, measurement quality, artifact manifest, OPE overlap — the platform
refuses to call itself production-ready without live proof.
