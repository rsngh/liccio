# Round 28 — Production Evidence, Guarded PRs, Operator Trust, Faster Tests

## Test acceleration (explicit hint)
- [x] pytest-xdist: parallelize the ~10min suite; keep pytest-in-pytest/docker tests stable

## Alpha 32 — guarded PR pipeline
- [x] build_draft_pr: verified draft -> acp/draft-* feature branch (never protected), PR
      description + rollback plan; unverified drafts blocked; zero protected-branch writes
- [x] LIVE: draft PRs over real-world tasks in sandbox branches

## Alpha 34 — operator cockpit / human review
- [x] `acp shadow inbox|show|label` over the persisted shadow-decision store
- [x] human label -> training data (accept/reject/override)

## Carry / earlier rounds (verified)
- [x] guarded execution ladder (draft patches, zero writes)
- [x] shadow-decision store (DB-persisted) + feedback->training

## Release
- [ ] report + full gate (xdist) + push
