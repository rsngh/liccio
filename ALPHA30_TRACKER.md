# Round 27 — Guarded Execution, Real-World Evidence, Operator Trust

Priority = move beyond recommend-only (guarded execution), grow real evidence. Live testing.

## Alpha 30 — guarded execution ladder (the #1 "what's missing")
- [ ] ExecutionMode ladder: shadow_only -> draft_patch -> draft_pr -> human_approved_apply
      -> human_approved_merge -> low_risk_autonomous_pr (DISABLED by default)
- [ ] guard() caps requested mode by policy; hard invariant: no apply/merge w/o approval
- [ ] produce_draft_patch: run agent in ISOLATION, verify in sandbox, NEVER apply
- [ ] LIVE: draft patches over real-world bug tasks; 0 writes to the working tree

## Alpha 27 — shadow decision store + human feedback -> training data
- [ ] ShadowDecision persisted as DB entity; human accept/reject captured
- [ ] human override -> training example

## Sample growth (carry-over)
- [x] reps=5 bakeoff (130 attempts); running reps=8 to push more cells robust

## Release
- [ ] report + full gate + push
