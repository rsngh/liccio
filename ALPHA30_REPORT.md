# Round 27 — Guarded Execution & Real-World Evidence Depth

Executing the round-27 plan's #1 gap: move beyond shadow/recommend-only into GUARDED
execution, while deepening observed-behavior evidence. Live testing throughout.

## Alpha 30 — guarded execution ladder (the headline)

`guarded_execution` adds the staged ladder the review demands:
`shadow_only -> draft_patch -> draft_pr -> human_approved_apply -> human_approved_merge ->
low_risk_autonomous_pr`. `guard()` caps a requested mode by a GuardrailPolicy:

- apply/merge require explicit human approval (else capped to draft_pr);
- `low_risk_autonomous_pr` is OFF by default and additionally needs low risk;
- any write-class mode needs sandbox + trusted measurement + a known verifier.

`produce_draft_patch` runs the agent in an ISOLATED sandbox repo, captures the diff, verifies
via the task's hidden tests, and NEVER touches the working tree (applied/merged stay False by
construction).

### Live proof

`run_guarded_execution_live` over the real-world repo-replay tasks: every task requested the
top of the ladder and the policy **capped all of them to draft_pr**. 5/5 draft patches
produced live (gpt-4o-mini), 3/5 verified in sandbox (paginate + lru_cache fail, consistent
with the systematic-failure finding). Hard invariants proven on the live run:
**no_autonomous_writes=True, nothing_applied=True, working_tree_unchanged=True**.

ACP can now produce and sandbox-verify draft patches without ever writing to a real tree —
the safe step beyond recommend-only.

## Sample growth (carry-over)

Larger reps=8 bakeoff: 208 conclusive attempts (was 130), **OPE log over 416 observed runs**
(was 260), mean cell Wilson-CI width tightened 0.38 -> 0.29; bugfix cells now n=40 at CI
[0.91, 1.0]. Honest finding: more reps tightens CIs and grows the OPE log, but the robust-cell
COUNT is bounded by task DIVERSITY (few tasks per non-bugfix type), not reps.

## Alpha 27 — shadow-decision store + human feedback -> training data

ShadowDecisionRecord is now DB-persisted (schema + ORM + migration). shadow_store provides the
operator inbox (save/query), record_human_feedback (accepted/rejected/overridden + outcome),
and feedback_to_training: an ACCEPTED recommendation is a positive label; a REJECTED/OVERRIDDEN
one is a corrective label pointing at the human's choice. inbox_summary reports acceptance rate
+ a zero-write audit. Every human override now becomes training data.

## Gate

```
uv run pytest -q --timeout=300
uv run ruff check . && uv run mypy src
uv run acp reports validate
uv run python evals/scripts/run_guarded_execution_live.py
```
