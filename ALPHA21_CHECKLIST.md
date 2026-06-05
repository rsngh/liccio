# Alpha 21 / Round 16 — Skill-Library Operating System Checklist

Status: COMPLETE (19/20 workstreams). Gate green: 942 passed, 5 skipped, ruff+mypy clean
across 255 source files, alembic OK, 46 artifacts valid. See `ALPHA21_REPORT.md`.

## Workstreams

- [x] WS1 — `acp reports sync-status` (report-truth automation)
- [x] WS2 — skill registry v2 (applicability/risk/required_tools/history/deployment_state)
- [x] WS3 — SkillOpt provenance graph (skill_provenance_runs; every skill line traceable)
- [x] WS4 — Microsoft SkillOpt backend hardening (config translator, importer, status)
- [x] WS5 — ACP internal SkillOpt parity (gate-action parity with real skillopt)
- [x] WS6 — production-grade starter skill suite (poison-clean)
- [x] WS7 — skill composition (safety order, conflict resolution, token budget)
- [x] WS8 — skill routing (composed skill set; selected/rejected explained)
- [x] WS9 — skill capability matrix (which skill works for task/harness)
- [x] WS10 — negative-transfer campaign (auto-narrow scope)
- [x] WS11 — staged skill canary platform (5/25/50/100% + guardrails)
- [x] WS12 — skill poisoning defense (8 categories; hard deploy block)
- [x] WS13 — cross-harness transfer study (portability classification)
- [x] WS14 — evolver budget study (diminishing-returns knee)
- [x] WS15 — topology + skill co-optimization (joint, safety-gated)
- [x] WS16 — relative trajectory judge for skill updates (8 axes)
- [x] WS18 — Docker live-security gate (9/9 checks; docker_live_security_passed=true)
- [x] WS19 — vendor-native harness live gate (codex+claude solve live; openhands health)
- [ ] WS17 — live corpus expansion (covered by prior 8-task-type / 100+ cell campaigns)

## Committed live artifacts (secret-scanned)

- [x] `evals/reports/docker_security_live.json` — passed, 9/9 checks
- [x] `evals/reports/vendor_harness_live.json` — available, passed, 2 solved
- [x] `reports/live/skillopt_run.json`, `skill_transfer.json`, `skill_canary.json`,
      `autonomous_cycle.json`

## Gate

```bash
uv run pytest -q --timeout=300         # 942 passed, 5 skipped
uv run ruff check . && uv run mypy src # clean (255 src)
uv run alembic upgrade head            # OK
uv run acp reports validate            # 46 artifacts valid
uv run acp eval docker-security-live   # passed (9/9)
uv run pytest tests/live -m live_vendor -q  # 2 passed (codex+claude live)
```
