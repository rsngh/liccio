# Round 28 — Alpha 31–41 completion tracker (delta-minimizing)

Goal: do/test EVERYTHING feasible; report achieved-vs-not-done delta at the end.

## Already done (earlier this round)
- [x] Alpha 32 guarded PR pipeline (live) ; Alpha 34 shadow inbox CLI ; xdist -n 2 gate

## To build this round
- [ ] Alpha 38 compute policy v2 (8 arms, variance-vs-systematic, MarginalValueReport, RiskValuePolicy)
- [ ] Alpha 39 skill economy v3 (SkillValueLedger, SkillMarket/competition, retirement)
- [ ] Alpha 40 harness-benefit training loop (activation/adherence datasets, PWL, adherence decay)
- [ ] Alpha 31 repo replay components (KnownFixVerifier, HiddenRegressionSuite, PatchEquivalenceJudge, PostMergeReplay, local-repo ingestor)
- [ ] Alpha 37 Kubernetes sandbox manifests (manifest gen + security validation; no live cluster)
- [ ] Alpha 36 deployment substrate (AuditLog, RBAC, Tenant)
- [ ] Alpha 41 policy graph warehouse (persist + repo_family signature + explorer)
- [ ] Alpha 32 ReviewerAssignmentPolicy ; Alpha 34 more verdicts
- [ ] Alpha 33 vendor corpus (opportunistic live; CLIs flaky -> honest scale note)

## Environment-blocked (cannot fully do here)
- Live GitHub ingest (no network/auth) -> local-git-history ingestor instead
- Live Kubernetes cluster -> manifest generation + validation only
- Postgres/object-store live deploy -> SQLAlchemy already supports postgres DSN; document
- LoRA (no GPU)
