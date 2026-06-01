# PR Readiness Checklist — Alpha 2

Label: `alpha` · `control-plane` · `needs-validation` · `do-not-merge-until-ci`

- [x] docs/test counts consistent (CURRENT_STATUS.md is source of truth)
- [x] CI config present (`.github/workflows/ci.yml`: ruff, mypy, unit+integration, e2e, coverage)
- [x] full run graph reconstructs from DB after process restart (`test_run_graph_full`, `test_merge_gate`)
- [x] exhaustive crash-resume passes (crash + exception after every node — `test_crash_resume_exhaustive`)
- [x] security red-team passes (`make security-redteam`, `test_security_redteam_expanded`)
- [x] Docker backend tested or explicitly skipped (`test_docker_workspace`, `test_docker_runner` — skip w/o daemon)
- [x] vector DB live tests skipped unless configured (Qdrant real-engine test runs; pgvector skipped w/o DSN)
- [x] eval reports generated + persisted as entities (`evals/reports/*.json`, `EvalRun`/`EvalReport`)
- [x] no production-grade overclaim (enforced by `test_merge_gate`)
- [x] known risks listed (CURRENT_STATUS.md "Known risks")
- [x] first true agent harness adapter (`OpenAIHarnessAdapter`, `is_harness=True`) — live-tested
- [x] routing policy persists across restarts + drift report (`test_policy_persistence`)
- [x] true concurrent soak (no DB corruption / orphan worktrees — `test_soak`)

## Committed artifacts (review without trusting verbal claims)

```text
reports/pytest.txt
reports/coverage.txt
reports/ruff.txt
reports/mypy.txt
evals/reports/context_benchmark.json
evals/reports/bakeoff.json
evals/reports/soak.json
```

## Merge only after
1. Full CI green on the PR.
2. CURRENT_STATUS.md reconciled with actual numbers.
3. Reviewer spot-checks a persisted run graph + an eval report.
