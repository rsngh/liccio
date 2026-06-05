# Alpha 22 — Production-Gated Live Harness & Skill Deployment Checklist

Status: COMPLETE (all 20 workstreams). Gate green: 961 passed, 5 skipped, ruff+mypy clean
(258 src), alembic OK, 46+ artifacts valid. See `ALPHA22_REPORT.md`.

## Workstreams

- [x] WS1 — release truth cleanup (sync-status, ALPHA21_CHECKLIST)
- [x] WS2 — Docker live-security artifact (passed, 9/9; production-gated)
- [x] WS3 — Docker contention hardening (unique names + labels + prune + retry)
- [x] WS4 — vendor harness live gate CLI + marker (live_vendor)
- [x] WS5 — vendor harness health detector
- [x] WS6 — vendor no-patch smoke fixture
- [x] WS7 — Codex CLI native harness adapter
- [x] WS8 — Claude Code native harness adapter
- [x] WS9 — OpenHands native harness adapter (health level)
- [x] WS10 — vendor skill-injection
- [x] WS11 — vendor measurement-trust integration
- [x] WS12 — vendor production-health gate
- [x] WS13 — staged canary persistence (survives restart)
- [x] WS14 — canary statistics (z-test + Bayesian beta-binomial)
- [x] WS15 — canary -> deploy/rollback integration
- [x] WS16 — vendor + SkillOpt live canary
- [x] WS17 — skill-aware vendor capability matrix
- [x] WS18 — cross-harness transfer live mini-study
- [x] WS19 — operator docs and scripts
- [x] WS20 — Alpha 22 release bundle (report + checklist)

## Live artifacts (secret-scanned, committed)

- [x] `evals/reports/docker_security_live.json` (passed, 9/9)
- [x] `evals/reports/vendor_harness_live.json` (passed, codex+claude solve)
- [x] `reports/live/vendor_skill_canary.json` (decision=hold; gate validated)
- [x] `reports/live/cross_harness_vendor_transfer.json`

## Operator commands

```bash
bash scripts/run_ws18.sh   # docker live-security
bash scripts/run_ws19.sh   # vendor harness live
uv run acp health --mode production
```
