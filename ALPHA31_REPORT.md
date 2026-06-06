# Round 28 — Guarded PRs, Operator Trust & Faster Tests

## Test acceleration (explicit hint) — pytest-xdist

Adopted `pytest-xdist -n 2` for the gate: **~5:44 vs ~9:44 serial (~40% faster)**, with NO
new flakes (the divide pytest-in-pytest contention flake didn't even trigger under the
better load distribution). Honest finding: `-n 4` OVERSUBSCRIBES — many tests spawn their own
`python -m pytest` subprocess (the benchmark/hard/repo_replay/guarded suites), so 4 workers ×
subprocess pytests thrash an 8-cpu box; `-n 2` is the sweet spot. Gate + CURRENT_STATUS
updated to `uv run pytest -q -n 2 ...`.

## Alpha 32 — guarded PR pipeline (draft patch -> draft PR)

`guarded_pr.build_draft_pr` takes a VERIFIED draft and applies it to a fresh `acp/draft-*`
feature branch (never a protected branch: main/master/production/release), commits, generates
a PR description, and produces a rollback plan. Unverified drafts are blocked.

**LIVE:** verified drafts (semver/deep_merge/normalize_path) became draft PRs on feature
branches; unverified (paginate/lru_cache) were blocked. 3/5 draft PRs,
`zero_protected_branch_writes=True`, `all_protected_branches_unchanged=True`. The safe rung
above draft_patch — drafts become PRs without ever writing a protected branch.

## Alpha 34 — operator cockpit (shadow inbox)

`acp shadow inbox|show|label` over the persisted shadow-decision store: inbox summary
(acceptance rate + zero-write audit), show a decision + policy dossier, and label
accept|reject|override — every override becomes corrective training data. Distinct from the
existing review studio (`acp reviews`).

## Gate

```
uv run pytest -q -n 2 --timeout=300      # ~40% faster
uv run ruff check . && uv run mypy src
uv run acp reports validate
uv run python evals/scripts/run_guarded_pr_live.py
uv run acp shadow inbox
```
