# Round 26 — Productionization, Real-World Evidence, Operator Trust

Priority = real-world evidence + AgensFlow coordination, with live testing.

## Alpha 33 — coordination policy graph v2 (AgensFlow centerpiece)
- [x] FoldedTaskSignature over the signature dimensions
- [x] PolicyGraph: signature -> action-value (conclusive rewards only), warm-start transfer
- [x] SkipXPolicy (skip:planner/retrieval/reviewer by signature; never skip verifier high-risk)
- [x] CrossJudgeRewardAudit can change a promotion

## Alpha 29 — real-repo replay (escape synthetic)
- [x] RepoReplayDataset: real-world-shaped historical bugs (pre-fix/known-fix/hidden tests)
- [x] LIVE: run OpenAI harness over replay tasks; tier=real_repo_replay
- [ ] routing differs meaningfully from synthetic; non-ceiling effects

## Alpha 30 — compute policy v2
- [ ] more arms (frontier_plus_verifier, human_escalation, abstain) + MarginalValueReport

## Alpha 27 — real-repo shadow
- [ ] RealRepoShadowRunner over actual git history; human-override store

## Release
- [ ] report + full gate + push
