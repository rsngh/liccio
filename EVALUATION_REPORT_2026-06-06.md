# Independent Evaluation Report — `agent-control-plane` (`acp` / liccio)

**Date:** 2026-06-06
**Branch:** `claude/hopeful-carson-xEoNq`
**Scope:** Complete testing + evaluation against the project's stated purpose, including
**live tests on unseen inputs** (real Claude API), with critical feedback and prioritized
next steps.

> Method note: this is a hands-on evaluation — every number below was produced by running the
> code in this environment, not read from prior reports. Live model calls used the real
> Anthropic API (`claude-sonnet-4-6`). OpenAI is **not reachable from this environment**, so
> OpenAI-path results are treated as an environment limitation, not a system defect.

---

## 1. Verdict

**The core product thesis works, and it works on inputs it has never seen.** Driven only by a
bug report, the control plane snapshots a repo, compiles a token-budgeted context pack, routes
to an agent, runs it in an isolated git worktree, **executes the repo's tests to verify**,
evaluates, computes a reward, and records a complete provenance chain. On **5 bugs authored
fresh for this evaluation** (absent from the repo), a real frontier model driven end-to-end by
`acp` solved **5/5** — each verified by execution **and** generalized to held-out inputs.

**But the repository over-states its green status.** The committed status advertises
*"1226 passed clean"*; a fresh full run in this container produced **14 failures**. None are
deep logic regressions — they decompose into (a) optional ML/SDK extras not installed, (b) test
coupling to generated artifacts that are git-ignored, and (c) one genuine robustness bug in the
**deploy** path (commit signing). I fixed the deploy bug and a measurement-contamination bug
during this evaluation; the rest are reproducibility/packaging hygiene that should be closed
before any "green" claim is trusted.

**Maturity:** strong **alpha / preproduction lab**, exactly as the repo's own docs say. The
empirical loop is real; the trust/reproducibility scaffolding around it is the weak point.

---

## 2. What was tested

| Dimension | Method | Result |
|---|---|---|
| Static quality | `ruff check .`, `mypy src` | **clean** (301 source files) |
| Full test suite | `pytest unit+integration+e2e -n2` (fresh env) | **14 failed, 1179 passed, 16 skipped** (455s) |
| Core loop (no keys) | `acp demo bugfix`, `acp demo bandit` | bugfix → `succeeded` w/ full provenance; bandit beats random (regret 58, 20/20 arms) |
| Health surface | `acp health` | renders lab readiness JSON |
| **Live, unseen inputs** | 5 fresh bugs → full loop w/ real Claude | **5/5 verified-green + generalized** |
| Live, real-world shapes | 3 repo-replay bugs → full loop w/ real Claude | **3/3 verified-green + generalized** |
| Robustness probe | no-op (already-correct) task → full loop | conservatively routed to human review, **code not regressed** |
| Multi-model breadth | OpenAI repo-replay live | **inconclusive** — OpenAI unreachable in this env (see §5) |

---

## 3. Headline strength — live evaluation on unseen inputs

This is the most important evidence because it tests the **whole system against its purpose**
on data it cannot have memorized. I authored five bugs that do **not** appear anywhere in
`src/` or `tests/` (verified by grep), each shipped as a real git repo with a buggy module, an
`ISSUE.md`, and a failing test. The reference fix is **never** shown to the agent — it only
proves offline that the task is solvable and fair (buggy → tests fail, reference → tests pass).

Three guards keep the pass/fail honest:
1. **Offline fairness** — buggy fails, reference passes (all 5 ✓).
2. **Execution truth** — "succeeded" means `acp` actually ran `pytest` and it passed.
3. **Generalization** — the model's captured diff is re-applied against a **held-out** test
   with inputs it never saw; passing rules out overfitting to the visible test.

| Unseen bug | Module | Verified green (acp ran pytest) | Generalized (held-out) |
|---|---|---|---|
| exponential backoff (linear vs `2**n`) | `backoff.py` | ✅ | ✅ |
| duration parser (drops hours) | `duration.py` | ✅ | ✅ |
| token-bucket limiter (burst over capacity) | `bucket.py` | ✅ | ✅ |
| CSV field escaping (RFC-4180) | `csvfmt.py` | ✅ | ✅ |
| binary search (misses last element) | `search.py` | ✅ | ✅ |

**5/5 solved**, all offline-fair, **provenance complete on every run** (snapshot / context pack
/ routing decision / attempt / evaluation / reward / trace IDs all present). Routing logged an
`action_probability` (0.33 — the bandit explored among strategy candidates) on each. Total live
spend was tiny: ~4.8k input / ~456 output tokens across the five.

The produced diffs are genuine algorithmic fixes, not test-pattern matching. Example
(`deep_merge`, from the companion real-world-shape run):

```diff
-    result.update(override)  # bug: nested dicts overwritten, not merged
+    for key, value in override.items():
+        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
+            result[key] = deep_merge(result[key], value)
+        else:
+            result[key] = value
```

Artifacts (committed, redacted, secret-scanned):
`evals/reports/eval_unseen_live.json`, `evals/reports/claude_control_plane_live.json`.
Reproduce: `ACP_ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY uv run python evals/scripts/run_eval_unseen_live.py`.

### Robustness probe (no-op)
Given a module that is **already correct**, the loop did not invent a spurious change: it
returned `waiting_for_human` and left the code green. Conservative behavior on an
under-specified task is the right default — though it should be made an explicit, tested
contract (see §6).

---

## 4. Test-suite reality vs. the advertised "1226 passed"

A fresh `pytest` run produced **14 failures**. Every one reproduces deterministically and
root-causes cleanly — **none are logic regressions**:

| # | Failures | Root cause | Class |
|---|---|---|---|
| 4 | `test_supervised_router` (×2), `test_evaluator_trust`, `test_learned_viability` | **scikit-learn / scipy not installed** → learned models fall back to a constant `0.5` predictor, so "beats random / separates" assertions fail | Env/packaging |
| 7 | `test_docs_consistency::test_alpha{6..12}_*`, `test_artifact_manifest_all_valid` | Reference report artifacts (`policy_dossier.json`, `harness_metrics.json`, …) are **git-ignored and absent on a fresh clone** | Artifact coupling |
| 1 | `test_guarded_pr::test_verified_draft_applied_…` | **Enforced commit signing** breaks `git commit` in the deploy path (signing server 400) → draft never applied | **Real bug** (fixed, §5) |
| 1 | `test_vendor_native::test_openhands_capability_level_reported` | OpenHands SDK not installed; test asserts `available is True` | Env/optional dep |
| 1 | `test_docker_contention_hardening::test_run_argv_has_unique_name_and_acp_label` | **Docker unavailable** → `AdapterUnavailable`; test asserts instead of skipping — yet its *sibling* docker tests skip correctly (inconsistent skip discipline) | Env/optional dep |

**Proof the ML failures are environment-coupling, not regressions:** after
`uv pip install scikit-learn joblib`, those **4 tests pass** (8 passed incl. parametrizations).
`scikit-learn` lives in the `data`/`learning` extras and `anthropic`/`openai` in `agents`; this
container was **not** synced with `uv sync --all-extras`, which the README assumes. The
failures are therefore a *reproducibility* problem, made worse because the tests **assert**
instead of **skipping** when the optional dependency is absent.

**Post-fix corroboration.** After applying the two fixes in §5 and installing the learning
extra, a full re-run yields **9 failed / 1184 passed / 16 skipped**. The 4 ML failures and the
`guarded_pr` failure are gone; the remaining **9 are all environment/artifact coupling** — the
7 git-ignored-artifact docs tests plus the 2 optional-dependency tests (OpenHands, Docker) that
assert instead of skipping. This confirms the categorization: **zero logic regressions; every
failure is reproducibility/packaging hygiene.**

---

## 5. Fixes applied during this evaluation

Two issues were concrete enough to fix and verify in-place:

1. **Deploy-path commit signing (real robustness bug).** `guarded_pr.build_draft_pr` and the
   shared `benchmark_suite._git_init` ran `git commit` without disabling signing. In any
   environment that *enforces* commit signing, the commit fails and the draft PR is silently
   left unapplied (`applied_to_branch=False`, `blocked_reason=None` — it doesn't even detect the
   failure). Fixed by committing sandbox-internal draft artifacts with
   `git -c commit.gpgsign=false`. `test_guarded_pr` now **passes (5/5)**.

2. **Measurement contamination on an unreachable provider.** `run_repo_replay_live.py` labeled
   every attempt `status="failed"` even when the provider was unavailable (`n_conclusive == 0`),
   so 25 inconclusive attempts were counted as **conclusive task failures** — publishing a
   `solve_rate_conclusive = 0.0` that reads as "the model failed every task." This is exactly
   the infra-poisoning the design warns against. The underlying `classify_attempt` is sound; the
   *harness* dropped the signal. Fixed by propagating each attempt's `_outcome` into the
   breakdown and surfacing `n_inconclusive` + a `measurement_contaminated` flag. The OpenAI run
   now correctly reports `n_conclusive: 0, n_inconclusive: 25, measurement_contaminated: true`
   instead of a fake 0% (this is also why the OpenAI breadth result is *inconclusive*, not a
   model verdict — OpenAI is unreachable here).

Both fixes are minimal, linted, type-checked, and covered by existing tests.

---

## 6. Critical feedback — what to fix next (prioritized)

**P0 — Make "green" reproducible. This is the trust blocker.**
- The suite must pass on a clean `git clone` + documented setup, or the headline number is not
  credible. Two concrete actions:
  - **Skip, don't fail, on absent optional deps.** Gate ML/SDK/daemon-dependent tests behind
    `pytest.importorskip("sklearn")` / `importorskip("openhands")` / a `docker_available()`
    skip (the live tests and *most* docker tests already do this — but
    `test_docker_contention_hardening` and `test_openhands_capability_level_reported` assert
    instead of skip, which is the actual bug). A missing extra/daemon should *skip*, never
    *assert-fail*.
  - **Decouple tests from generated artifacts.** `test_docs_consistency` asserts that
    git-ignored report JSONs exist on disk. Either (a) generate them via a `make
    pre-test-artifacts` step the suite depends on, or (b) assert the *checklist references* a
    path without requiring the file, or (c) commit a small canonical subset. As written, these
    7 tests can only pass on the machine that last ran the eval campaign.
- Pin what "clean" means in CI: run `uv sync --all-extras` and publish the exact pass/skip
  counts the suite yields from a fresh checkout.

**P1 — Refresh stale trust artifacts.**
- `reports/coverage.txt` and several `ALPHA*`/`ROUND*` reports advertise counts ("1226 passed
  clean") that don't reproduce here. Regenerate them from a clean run, or label them clearly as
  "captured in the dev environment with all extras." GOALS.md §4 already flags the stale
  coverage artifact — it is still stale.

**P2 — Harden the deploy rung beyond the one bug fixed.**
- `build_draft_pr` should **detect** a failed commit (check `git commit` return / verify
  `head != base`) and return an explicit `blocked_reason` instead of a silent
  `applied_to_branch=False`. The signing failure surfaced this gap: the deploy step can fail
  without saying why.
- The guarded-PR path is the closest thing to "deploy"; it deserves a negative-path test for
  *every* way the sandbox commit can fail (signing, dirty tree, detached HEAD).

**P3 — Make the live measurement harnesses contamination-proof by construction.**
- The `classify_attempt` machinery is good, but it only helps if every live script routes
  outcomes through it. Audit the other `evals/scripts/*_live.py` for the same
  "label-as-failed" shortcut I fixed in `repo_replay_live`. Consider a single
  `cells_from_results()` helper so no script hand-rolls cell construction.
- Surface `measurement_contaminated` / `n_inconclusive` in `acp health` and refuse to ingest
  contaminated cells into the capability matrix (GOALS WS1/WS8 acceptance).

**P4 — Close the gap between the default registry and the real adapters.**
- `acp agents list` shows only `fake`/`patch` by default; the real Claude/OpenAI adapters exist
  and work (this eval drove Claude through the full loop) but are not registered unless a caller
  wires them. A first-class `acp agents enable claude` / config-driven registry would make the
  live capability discoverable rather than something an evaluator has to assemble by hand.

**P5 — Turn the no-op behavior into a tested contract.**
- "Already-correct task → human review, no spurious diff" is good behavior but currently
  incidental. Add an explicit abstention/no-op test so it can't silently regress into either a
  false fix or a false "succeeded".

---

## 7. Assessment against intended purpose

The README's thesis is *"route → attempt → verify → evaluate → learn, turning every run into a
reusable training example."* Measured against that:

- **Route / attempt / verify / evaluate / reward / provenance:** ✅ demonstrated live on unseen
  inputs, end-to-end, with execution-based verification and complete, queryable lineage.
- **Learn (routing improves):** ✅ in simulation (bandit beats random, 20/20) — but the live
  learning loop is still thin on *real* cells; the capability matrix is fed mostly by
  synthetic/fixture evidence, and the one live multi-model comparison available here was
  blocked by network, not exercised. This remains the most important thing to grow (GOALS
  WS8/WS19).
- **Multi-agent / multi-model:** partially proven. The Claude path is fully live; the OpenAI
  path is unreachable in this environment, so the comparative-routing claim that motivates the
  product is asserted but not independently reproduced here.

**Bottom line:** the engine is real and behaves correctly on novel work; the surrounding claims
of a clean, reproducible, multi-model green build are ahead of what a fresh checkout
demonstrates. Closing the P0/P1 reproducibility items would let the impressive live results
speak without an asterisk.

---

## Appendix — commands run

```bash
uv run ruff check . && uv run mypy src                      # clean (301 files)
uv run pytest tests/unit tests/integration tests/e2e -n2    # 14 failed / 1179 passed / 16 skipped
uv run acp demo bugfix && uv run acp demo bandit            # core loop OK
ACP_ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  uv run python evals/scripts/run_eval_unseen_live.py       # 5/5 unseen, verified + generalized
ACP_ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  uv run python evals/scripts/run_claude_control_plane_live.py  # 3/3 real-world shapes
uv pip install scikit-learn joblib                          # -> the 4 ML tests then pass
```

Artifacts produced/updated by this evaluation:
`evals/reports/eval_unseen_live.json`, `evals/reports/claude_control_plane_live.json`,
`evals/reports/repo_replay_live.json` (now contamination-flagged).
