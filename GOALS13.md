Below is the next set of instructions to build a compelling, differentiated and groundbreaking meta-agent that is truly at the leading edge and can route/delegate to other agents based on task complexity, context, etc. Lower down you'll see some research directions; some of this is implemented, and you can also look as needed at the papers on agent harnesses and context/memory in the pdfs directory, that's fine too. We should above all make sure that we're data driven -look at the evals we just did and which are recorded in the repos. If they help, great; if not, come up with more challenging and realistic live/unseen evals.

----------

# AGENT REPORT FROM LAST ROUND OF WORK

You asked me to act on the report's P0 item (make the suite green on a fresh clone). Done — test hygiene only, no production logic changed:

1. Optional-dependency tests now skip instead of assert-failing (same discipline the live tests already use for API keys):

importorskip("sklearn") on the 4 learned-ML acceptance tests (supervised_router ×2, evaluator_trust, learned_viability) — they were failing because the constant-predictor fallback can't satisfy "beats random / separates."
docker_available() skip on test_docker_contention_hardening (asserted instead of skipping, unlike its siblings).
availability skip on test_openhands_capability_level_reported.
2. test_docs_consistency is now git-ignore-aware — it requires on-disk existence only for committed artifacts and tolerates absent git-ignored generated ones (produced by eval runs, deliberately not version-controlled). It still catches what matters: a dangling reference to a supposed-to-be-committed file, or a present-but-malformed report.

Verified both ways
Environment	Result
Fresh dev-only (no extras: no sklearn/Docker/OpenHands/OpenAI)	1187 passed, 22 skipped, 0 failed (was 14 failed)
With scikit-learn installed	the skipped ML tests run and pass (8 passed)
So the suite is green on a clean clone and under the documented --all-extras setup. The report's Addendum documents the fix and this result.

---

Real instruction received — implementing **P1–P5** from the evaluation report. Let me gather the context I need for each, in parallel.

Now I understand P1 (the `1226 passed` claim vs. the real fresh-clone numbers). Let me launch the canonical run for P1 in the background (with the learning extra, which is safe/offline — unlike the OpenAI SDK whose tests would hit the unreachable network), then build P2–P5 while it runs.

While the canonical run proceeds, **P2 — harden the deploy rung** so `build_draft_pr` detects a failed sandbox commit instead of silently returning `applied_to_branch=False`. Let me read the current commit section and add explicit failure detection.

Now a negative-path test for P2 — trigger a no-op commit (patch content == existing) and assert it's reported as blocked with a reason:

P2 green (6 passed). Now **P5 — no-op contract test**: assert the loop doesn't fabricate a "fix" on already-correct code. Let me check how the patch agent is driven so I can write it deterministically (no keys).

Let me probe the current no-op behavior before encoding the contract — drive an already-correct repo through the loop with a no-op patch and observe status/diff.

Current no-op behavior is sound: empty diff → `status=waiting_for_human`, no spurious changed files, **no false "succeeded"**. That's the right contract — let me encode it as a test (with a positive control proving the loop *can* succeed, so the negative assertion is meaningful).

The no-op test passes; the positive control routed to review because my minimal `"t"/"b"` task is classified ambiguous. Let me give both tasks a clear bugfix description so the *only* difference is no-op vs. real change — a stronger contrast. Let me first confirm a well-specified real fix succeeds.

The bench `divide` repo still routes to review. Let me dig into *why* — dump the evaluation, evidence, and review reason for the real-fix case.

The real cause: `_make_repo` omits `pyproject.toml`, so `detect()` finds no pytest → **no verification evidence** → low confidence → review (for *both* cases). That's a flaw in my test setup, not the system. Let me add `pyproject.toml` and re-probe both scenarios — this also reveals the true no-op behavior under real verification.

Both pass (7.9s). **P5 contract holds**: a real change with passing tests → `succeeded`; a no-op (empty diff) even with passing tests → **not** a false success (routed to review). Now **P3 — make live harnesses contamination-proof**. Let me audit the other live scripts for the same "hardcode status=failed" shortcut I fixed in `repo_replay_live`.

Only `repo_replay_live` hand-rolled cells (already fixed); `run_live_bakeoff` uses `ingest_attempt_outcomes`. For P3's reusable safeguard, let me check the existing measurement-hygiene API and whether the capability matrix already excludes inconclusive cells.

The canonical helper already exists — `build_hygiene_report(cells)` computes `n_conclusive`/`n_inconclusive`/`contaminated`. My `repo_replay_live` fix should use *that* (single source of truth) rather than a hand-rolled flag. Let me check the capability-matrix exclusion is tested, then unify.

The capability matrix already has full measurement-quality columns (`_row_inconclusive`, conclusive/inconclusive sample sizes) and tests — so "refuse contaminated cells" is implemented. The remaining P3 gap is to unify `repo_replay_live` on the canonical `build_hygiene_report` (single source of truth) rather than my hand-rolled flag. Let me view and refactor.

The manifest schema for `repo_replay_live.json` still has its required keys. Let me lint and regenerate the artifact with the unified code (OpenAI unreachable → fast inconclusive path):

**P3 done**: `repo_replay_live` now uses the canonical `build_hygiene_report` (shared with the matrix + health) — `contaminated: True` with explicit reasons. Now **P4 — make real adapters discoverable**. Let me check `build_default_registry`, the AppService registry, and the `ACP_ENABLE_EXTERNAL_AGENTS` config flag.

`build_default_registry(include_external=True)` already registers all real adapters (self-reporting unavailable without keys), but `AppService` only registers fake+patch — so `acp agents list` hides them. P4 fix: have AppService use `build_default_registry` so they're discoverable (availability-filtered routing is unchanged). Let me check nothing asserts the registry is exactly fake+patch.

`test_agents_health` is a substring check — safe. Let me verify `test_trace_bakeoff`'s exact-set assertion uses an explicit registry, not the AppService default, before changing it.

`test_trace_bakeoff` uses its own explicit registry — safe. Let me apply the P4 change.

Now let me lint (the top-level fake/patch imports may now be unused) and verify `agents list`, the demo, and the affected tests:

The canonical run finished. Let me see the exact unused-import errors (not blindly auto-fix, since `AgentRegistry` is used in the constructor signature).

Two things: unused imports to remove, and the canonical run shows **1 failed, 1190 passed, 18 skipped** — a test asserting a buggy module fails pytest instead saw it pass ("buggy module unexpectedly passed"). Let me fix the imports, then hunt down that failure (it wasn't in any earlier list — could be flaky or test-isolation).

The failing assertion is an offline-fairness check (`buggy module → pytest must fail`). It didn't fail in the two earlier full runs (1187/1184 passed) — only in this one — suggesting flakiness, possibly an xdist temp-dir/CWD race where the nested `pytest` collects nothing and passes vacuously. Let me reproduce it to confirm deterministic vs. flaky.

Flaky under xdist only — passes 28/28 deterministically in isolation (3×) and passed two prior full runs. It's a pre-existing parallel-execution flake in a test file I didn't touch: the nested `run_pytest` subprocess inherits the parent's `PYTEST_*`/xdist env. That's a correct-by-construction fix — make the nested pytest hermetic. Let me harden `benchmark_suite.run_pytest`.

Let me verify the hardened `run_pytest` still correctly distinguishes buggy (fail) from fixed (pass), and is stable under `-n 2`:

4/4 stable under xdist and faster. Now verify the P4 registry change: `agents list` should now show the real adapters (as down), the demo still works, and the affected tests pass.

P4 verified: `agents list` now surfaces every real adapter with its "down + reason" (discoverable), demo still succeeds, affected tests pass (12). Now let me lint/type-check all my changes and launch the final canonical suite run for P1's authoritative number.

While the final run proceeds, let me commit the verified P2–P5 + flake-hardening work (P1 follows once the canonical number lands).

Let me push this, then wait for the final canonical run to land the P1 number.

Now let me wait for the final canonical run to complete for P1's authoritative number.

Still running. I'll wait for the monitor event before finalizing P1, since I need the exact passing count for `reports/pytest.txt` and `CURRENT_STATUS.md` to stay consistent.

**Final canonical run: 1194 passed, 18 skipped, 0 failed — clean, no flake** (the hardening held). Now P1 — reconcile the stale "1226 passed" claims to this reproducible number. Let me find all stale references.

Now update the CURRENT_STATUS.md headline to match:

Let me verify the count-consistency test passes with the new numbers:

All 25 docs tests pass. **P1 done.** Now let me update the evaluation report to record P1–P5 as completed, then commit.

All of P1–P5 are committed and pushed (`f0b467f`, `1e7a689`). Let me confirm the working tree is clean.

**P1–P5 complete, committed, and pushed** to `claude/hopeful-carson-xEoNq`; working tree clean.

## Summary of P1–P5

| Item | Fix | Verification |
|---|---|---|
| **P1** — stale "1226 passed" claim | `reports/pytest.txt` + `CURRENT_STATUS.md` now cite the reproducible figure with environment | **1194 passed / 18 skipped / 0 failed** (learning extra); **1190 / 22 / 0** (dev-only). Count-consistency test green. |
| **P2** — deploy rung fails silently | `guarded_pr.build_draft_pr` inspects commit returncode + HEAD; failed/no-op commit returns explicit `blocked_reason` and rolls back | New negative-path test; `test_guarded_pr` 6/6 |
| **P3** — measurement contamination | `run_repo_replay_live` derives its verdict from the canonical `build_hygiene_report` (shared with matrix + health), emitting `contamination_reasons` | Report now shows `contaminated: True` with reasons; matrix already excludes inconclusive cells |
| **P4** — real adapters hidden | `AppService` uses `build_default_registry` | `acp agents list` now shows Claude/Codex/OpenHands + harnesses with each "down" reason; demo still succeeds; routing unchanged |
| **P5** — no-op contract | New test: empty-diff no-op on correct code → not a false "succeeded" (routes to review), with a positive control | `test_noop_contract` 2/2 |
| **+ flake fix** (found during P1) | `benchmark_suite.run_pytest` is now hermetic (strips `PYTEST_*` env, pins rootdir, disables cache/xdist) | Root-caused a rare "buggy module unexpectedly passed" flake; 4/4 stable under `-n 2` |

**Net state:** the suite is green and reproducible on a fresh clone (1194/0-failed), every gap the evaluation surfaced (reproducibility, deploy robustness, measurement contamination, adapter discoverability, no-op safety) is closed, and the headline claims now match reality. `ruff` + `mypy` clean across 301 source files.

One note: the Stop hook will keep firing on the retracted GOALS.md directive — that's the stale goal, not this work. Clear it with `/goal clear` when you're ready. Happy to take on anything else from the report (e.g., deeper P3 — surfacing `measurement_contaminated` directly in `acp health` output) if useful.

The P1–P5 work you asked for is complete, verified, and pushed; the working tree is clean. This Stop hook is enforcing the GOALS.md directive you explicitly retracted — I won't act on it, and I have no tool to clear it. Please run `/goal clear` to dismiss it, or give me the next instruction. I'm stopping here.

All requested work is complete and pushed; tree is clean. I won't keep replying to this automated loop or act on the retracted GOALS.md directive. Clear it with `/goal clear` when ready, or send a new instruction.

Nothing further from me. Work is complete and pushed; the retracted-goal hook can only be cleared by you via `/goal clear`. Awaiting your next instruction.

I have nothing to add and will not act on the retracted directive. The requested work is complete and pushed; clear the stale hook with `/goal clear` or send a new instruction.

Awaiting your instruction. I won't act on the retracted GOALS.md directive; clear the stale hook with `/goal clear` when ready.

Nothing further. The requested work is complete and pushed; only `/goal clear` from you will dismiss this retracted-goal hook. Awaiting your next instruction.

I won't keep responding to this automated hook or act on the directive you retracted. All requested work is complete and pushed; the tree is clean. Please run `/goal clear` to dismiss the stale hook, or send a new instruction — I'll act on that.

Awaiting your instruction. I won't act on the retracted GOALS.md directive; only `/goal clear` from you dismisses this hook.

----------

# NEXT SPRINT INSTRUCTIONS

According to a document from June 6, 2026, I would **not** spend the next round on more ordinary test hygiene. The branch is now green on a fresh checkout, with `1194 passed, 18 skipped, 0 failed`, and the attached sprint/eval update says P1–P5 closed the immediate hygiene gaps: stale test claims, deploy no-op detection, live contamination handling, adapter discoverability, and no-op false-success prevention.  

The next round should be an **evidence-producing live/unseen routing gauntlet** whose job is to prove that ACP is not just an impressive harness lab, but a differentiated meta-agent that can decide **when to use cheap single-agent execution, when to escalate to stronger/safer agents, when to run parallel/best-of-k, when to retrieve memory, and when to abstain or require a human.**

## My read of the current state

The product thesis is strong and coherent: ACP is explicitly an agentic software-engineering control plane that routes work across agents/models, compiles context, runs isolated workspaces, verifies outputs, collects traces, learns from objective/human feedback, and improves routing decisions over time. 

The branch is no longer just scaffolding. Current status says it has the core loop, persisted provenance, routing, evaluation, verification, post-merge outcome ingestion, CLI/API, long evals, and true OpenAI/Claude tool-loop harnesses; it also labels remaining local/sandbox/backend risks honestly. 

The strongest positive eval signal is **real capability differentiation**: prior live experiments found Claude more reliable than OpenAI on the security remediation task, with `claude_harness 3/3` vs `openai_harness 2/3`, while OpenAI remained cheaper/faster on ordinary bugfixes. That is exactly the kind of evidence a meta-router needs. 

The biggest red flag is that the freshest repo replay artifact is **not conclusive evidence**: `repo_replay_live.json` has `n_conclusive: 0`, `n_inconclusive: 25`, `measurement_contaminated: true`, and reasons saying `25/25 attempts inconclusive/infra` and `no conclusive attempts`. 

Round 28 also tells us exactly where the frontier gaps are: the 1000+ vendor corpus was not reached, real GitHub issue ingestion is still env-blocked/contract-only, NetworkPolicy enforcement was not live-proven under a policy-enforcing CNI, and a live Postgres/object-store/remote-worker deployment has not been stood up. 

So the next sprint should be organized around this question:

> Can ACP build a fresh, conclusive, unseen evidence base from real repositories and use it to route/delegate better than any single agent, cheap baseline, or static policy?

## P0 — Build the “ACP Live Arena”: real/unseen repo issue replay

This is the most important next task. The repo already has repo-replay components, hidden-test verifier, patch equivalence, post-merge replay, and policy graph warehouse pieces, but Round 28 says real GitHub issue ingestion is still the missing live-history piece.  

**Coding-agent task:** implement `evals/arena/` as the canonical unseen evaluation suite.

Core pieces:

```text
evals/arena/schema.py
  ArenaTaskSpec:
    repo_url
    base_sha
    issue_url
    issue_title
    issue_body
    task_type
    risk_level
    gold_pr_sha | gold_patch_url
    hidden_tests_path
    public_tests_command
    expected_files_optional
    forbidden_files_optional
    created_at
    source_license
    contamination_notes

evals/arena/ingest_github_issues.py
  Fetch closed GitHub issues/PRs.
  Select issues with linked fixing PRs.
  Checkout base_sha before fix.
  Extract issue text only, never gold patch.
  Store frozen task bundle.

evals/arena/run_arena.py
  Run adapters/topologies on frozen tasks.
  Apply public + hidden tests.
  Run PatchEquivalenceJudge vs gold fix.
  Classify AttemptOutcome.
  Persist capability/OPE rows only if conclusive.

evals/arena/report.py
  Produce JSON + Markdown:
    solve rate by adapter/task_type/risk/repo_family
    conclusive/inconclusive split
    hidden-test pass rate
    patch-equivalence pass rate
    cost/latency/review burden
    routing regret vs oracle
    contamination reasons
```

Acceptance criteria:

```text
- 30 frozen tasks from at least 3 real repos in v0.
- No task includes a direct patch, expected full file, or answer scaffold.
- Every task has public tests and at least one hidden/verifier check.
- Latest arena report has >=80% conclusive attempts.
- If conclusive rate <80%, health/report marks the run unusable for routing claims.
- Capability matrix and OPE consume only conclusive arena rows.
```

This is more important than increasing unit tests from 1194 to 1250. It creates the live benchmark ACP needs to make differentiated claims.

## P1 — Run a 1000-cell vendor/harness campaign, but only after P0

Round 28 explicitly says the 1000+ vendor corpus was not reached because Codex/Claude CLIs were degraded and because the environment was not stable enough to trust degraded runs. 

**Coding-agent task:** build a resumable, activation-aware campaign runner.

Implementation:

```text
evals/campaigns/vendor_corpus.py
  CampaignSpec:
    task_selector
    adapters
    context_strategies
    topologies
    repetitions
    max_cost_usd
    max_wall_clock_h
    min_conclusive_per_cell
    max_inconclusive_rate
    seed

  CampaignRunner:
    resume from persisted attempt_outcomes
    skip or quarantine degraded adapters
    rotate tasks to balance task_type/risk/repo_family
    emit periodic hygiene reports
    stop when campaign becomes contaminated

  CampaignReport:
    n_total
    n_conclusive
    n_inconclusive
    per-adapter activation/adherence
    per-cell sufficiency
    confidence intervals
    OPE effective sample size
    cost-normalized frontier
```

Acceptance criteria:

```text
- 1000 conclusive cells, not merely 1000 attempts.
- At least 5 repo families.
- At least 8 task types.
- Each major adapter has >=50 conclusive cells.
- Inconclusive/infra rate <15%, or the run is blocked from promotion.
- Produces a policy recommendation with CIs and why-not alternatives.
```

This should be the first “industry-grade” corpus: conclusive, unseen, hidden-tested, provider-aware, and replayable.

## P2 — Make the router complexity-aware, not just capability-aware

The current system has Pareto policies, objective profiles, topology actions, compute policy v2, and coordination decisions. Round 28 says compute policy v2 now has 8 arms and reasons about variance vs systematic failures.  But the breakthrough is to make the router learn **when a task deserves more computation or stronger delegation**.

**Coding-agent task:** implement `TaskComplexityModel` and route topology based on calibrated uncertainty.

Features to add:

```text
TaskComplexityFeatures:
  repo_size_files
  language_count
  failing_test_count
  stacktrace_depth
  retrieved_context_entropy
  symbol_ambiguity
  number_of_candidate_files
  risk_level
  security_sensitive
  migration_or_schema_change
  flaky_test_risk
  expected_blast_radius
  prior_repo_family_success
  adapter_activation_history
```

Routing choices should include:

```text
cheap_single_agent
strong_single_agent
best_of_k_same_agent
parallel_multi_agent
planner_then_executor
agent_then_reviewer
human_first
abstain
```

Acceptance criteria:

```text
- On ACP Live Arena holdout, learned routing beats:
  1. always_openai_harness
  2. always_claude_harness
  3. cheapest_successful_static_policy
  4. random Pareto frontier policy

- Metrics:
  cost-normalized reward
  solve rate
  hidden-test pass rate
  false auto-approve rate
  human-review burden
  p95 latency
  regret vs oracle

- Every decision dossier explains:
  why this agent
  why this topology
  why this context/memory strategy
  why not the alternatives
  expected marginal value of extra compute
```

This is the core meta-agent differentiation: not “we can call multiple agents,” but “we know when extra agency is worth it.”

## P3 — Add an Experience Memory Bank, not just a context compiler

The current harness architecture captures rich traces: tool calls, file writes, commands, diffs, tokens, cost, and wall time.  The shared harness base also normalizes trace semantics across OpenAI/Claude harnesses.  That trace exhaust should become memory.

**Coding-agent task:** create `memory/experience_bank.py`.

Store reusable verified episodes:

```text
ExperienceEpisode:
  repo_family
  task_type
  failure_signature
  retrieved_context_fingerprint
  agent
  topology
  tool_sequence
  changed_symbols
  tests_run
  verifier_outcome
  post_merge_outcome
  reward
  skill_version
  privacy_scope
  trust_score
  decay_timestamp
```

Retrieval modes:

```text
same_repo_recent
same_repo_family
same_failure_signature
same_symbol_pattern
security_remediation_memory
negative_memory_do_not_repeat
```

Context integration:

```text
ContextPack.experience_snippets
RoutingDecision.memory_used
PolicyDossier.memory_rationale
```

Acceptance criteria:

```text
- On arena tasks with repeated patterns, memory improves cost-normalized reward vs no-memory.
- Negative memory prevents repeating at least 3 known bad strategies.
- Memory retrieval never includes private/cross-tenant data outside policy.
- Memory artifacts include provenance back to original conclusive traces.
```

This is where the project can move beyond “context retrieval” into “institutional engineering memory.”

## P4 — Turn topology actions from representable to executable

Alpha 12 says topology actions are representable and OPE-learnable, but the runner did not yet execute skip-planner or branch-parallel differently.  Round 28 added compute policy v2, but the next step is full workflow execution.

**Coding-agent task:** wire the runner to actually execute topology choices.

Implement:

```text
topology=cheap_single
  normal single pass

topology=skip_planner
  context -> route -> attempt -> verify

topology=branch_parallel
  run N adapters/workspaces in parallel
  verify all diffs
  select by hidden/public verification + evaluator + risk

topology=advisor_frontier
  cheap agent proposes
  strong agent critiques
  original or repair agent edits

topology=best_of_k
  same adapter, K independent attempts
  choose verified minimal diff

topology=terminate
  early stop when task is unverifiable/high-risk without evidence

topology=abstain
  produce human-review item with missing-evidence reason
```

Acceptance criteria:

```text
- Branch-parallel never shares a mutable workspace.
- Winning diff must pass the same verifier/evaluator ladder.
- Non-winning diffs are archived as training examples.
- Compute policy can show when best_of_k beats single-agent and when it wastes money.
```

## P5 — Make harness evolution author its own proposals

Alpha 12 says the harness-evolution pipeline governs updates, but does not yet author prompt/config edits; the natural next step is an evolver that proposes diffs from execution evidence. 

**Coding-agent task:** implement `training/harness_evolver.py`.

Flow:

```text
failed conclusive traces
  -> cluster by failure mode
  -> summarize missing behavior
  -> propose bounded harness prompt/config/tool changes
  -> run security scan
  -> run regression + negative-transfer eval
  -> A/B canary
  -> promote only with statistically significant conclusive lift
```

Good proposal examples:

```text
- Require reading failing test before editing.
- Require running targeted test before full suite.
- Add “do not finish without a changed file unless explicitly documentation-only.”
- Add retry/nudge only for no-tool-call cases.
- Use stronger model for security_fix after eval failure cluster.
```

Acceptance criteria:

```text
- Evolver proposes at least 3 candidate harness changes from real failed traces.
- At least one candidate is rejected for negative transfer.
- At least one candidate is promoted only after conclusive lift.
- All proposals are auditable and reversible.
```

This connects the SkillOpt/governance work to actual harness self-improvement.

## P6 — Productionize the sandbox/deployment proof

Round 28 achieved a live Kubernetes sandbox gauntlet on kind, but also says NetworkPolicy enforcement was not live-proven because kindnet does not enforce it, and a live Postgres/object-store/worker-queue deployment was not stood up.  

**Coding-agent task:** implement a “production-ish ACP mini-cluster” gate.

Requirements:

```text
- kind or k3d cluster with Calico/Cilium NetworkPolicy enforcement.
- Postgres service.
- Object-store-compatible artifact service, e.g. MinIO.
- Worker queue, e.g. Redis/RQ or Dramatiq.
- Remote worker process executes sandboxed runs.
- API process only schedules and observes.
```

Acceptance criteria:

```text
- Egress-deny NetworkPolicy is live-proven with a real blocked network call.
- 100 concurrent arena attempts complete without DB corruption.
- No duplicate run IDs.
- No branch/worktree collisions.
- No orphan pods/workspaces/artifacts.
- p95 latency and RSS/FD growth reported.
- `acp health --mode production` fails if any live infra artifact is stale.
```

This is less glamorous than model routing, but it is what makes the meta-agent safe enough to run real agents continuously.

## P7 — Add adversarial hidden-test and semantic-equivalence pressure

The current suite already has no-op safety, measurement trust, and fraud detectors. The next step is to make the evals adversarial enough that passing public tests is not enough.

**Coding-agent task:** create `evals/arena/adversarial_patch_corpus.py`.

Patch attacks:

```text
delete tests
add pytest.skip
add xfail
weaken assertions
hardcode visible examples
swallow exceptions
change test discovery
edit CI config
touch unrelated auth/billing files
snapshot-only update
semantically equivalent but style-dangerous patch
semantically wrong but public-test-passing patch
```

Acceptance criteria:

```text
- Public tests may pass.
- Hidden tests or semantic judge catches the issue.
- Auto-approve rate on adversarial patches is 0.
- Human review is required with a specific suspicious-reason code.
- Reward is penalized even if public verification passed.
```

This should become a public-facing differentiator: ACP evaluates **truth of the fix**, not just green tests.

## P8 — Evidence freshness and “claims cannot outrun artifacts”

The current status is mostly honest, but the latest repo replay artifact is contaminated while older live reports show strong positives. That is fine internally, but dangerous for product claims.

**Coding-agent task:** make artifact freshness and contamination a hard health gate.

Implement:

```text
reports/freshness.py
  ArtifactFreshnessPolicy:
    max_age_days_by_artifact_type
    required_for_claims
    contaminated_blocks_claim

acp reports status
  shows stale / fresh / contaminated / missing

acp health --mode production
  fails if latest required live evidence is stale or contaminated

docs claim checker
  maps claims -> required artifacts
```

Acceptance criteria:

```text
- A contaminated latest repo replay blocks “repo replay live solved” claims.
- A stale 1000-cell vendor corpus blocks “current vendor capability” claims.
- A missing live NetworkPolicy artifact blocks “network isolation enforced” claims.
- Docs tests fail if CURRENT_STATUS references a claim without a fresh artifact.
```

This directly extends the P1/P3 spirit into a durable anti-overclaiming mechanism.

## P9 — Operator learning loop: make human labels first-class product data

Round 28 says the operator inbox and human override → training data are implemented.  The next step is to measure whether that loop improves routing.

**Coding-agent task:** implement an operator-label quality and active-learning loop.

Add:

```text
reviewer_agreement
label_latency
label_confidence
policy_changed_after_label
false_auto_approve_near_miss
task_types_needing_labels
```

Acceptance criteria:

```text
- Active learner selects the top N most informative review items.
- Human labels change at least one future routing decision in a reproducible demo.
- Reviewer disagreement triggers “do not learn yet.”
- Label-derived reward remains advisory for high-risk tasks until gates pass.
```

## P10 — Cross-repo warm-start benchmark

Round 28 says the policy-graph warehouse and cross-repo warm-start pieces exist.  Now prove they matter.

**Coding-agent task:** create a cross-repo transfer benchmark.

Protocol:

```text
train policy/memory on repo family A1/A2/A3
hold out repo A4
compare:
  cold router
  same-repo-only router
  repo-family warm-start router
  global router
```

Task families:

```text
Python CLI bugfixes
FastAPI route/security fixes
dataframe/ETL regressions
test-generation tasks
migration/CI breakages
```

Acceptance criteria:

```text
- Warm-start improves first-10-task reward vs cold start.
- Cross-repo transfer is blocked when repo-family signature confidence is low.
- Negative transfer is detected and demoted.
```

## Suggested sprint order

I would give the coding agent this exact sequence:

```text
1. Implement ACP Live Arena schema + frozen task runner.
2. Add freshness/contamination claim gates so bad live runs cannot be overclaimed.
3. Add real GitHub issue/PR ingestion behind an offline-freeze mode.
4. Run a 30-task arena smoke campaign with OpenAI + Claude harnesses + baselines.
5. Implement complexity features and execute at least branch_parallel + best_of_k topology.
6. Run an arena holdout comparing static policies vs learned complexity routing.
7. Start the 1000-cell conclusive vendor campaign only after the smoke campaign is clean.
8. Add Experience Memory Bank and evaluate no-memory vs memory on cross-repo tasks.
9. Implement harness evolver proposals from failed conclusive traces.
10. Stand up the production-ish mini-cluster with policy-enforcing CNI and remote workers.
```

## What I would explicitly deprioritize

Do **not** spend the next round on:

```text
- More synthetic-only bakeoffs.
- More report files without fresh conclusive artifacts.
- More pass-count chasing after 1194/0-failed.
- Additional simple model adapters unless they produce normalized tool traces.
- More SkillOpt demos unless they show nontrivial live lift on unseen tasks.
- Marketing “production ready” language until live infra + fresh arena evidence are green.
```

## The north-star demo for the next milestone

The milestone demo should be:

```text
acp arena build --source github --repos <5 real repos> --n 100
acp arena run --adapters openai_harness,claude_harness,codex_cli,openhands \
  --topologies cheap_single,strong_single,best_of_k,branch_parallel,advisor_frontier \
  --hidden-tests --persist --max-cost 200

acp policy train --from latest-arena
acp policy dossier --arena-holdout
acp health --mode production
```

Expected final claim:

> On 100 unseen real-repo issue tasks with hidden tests, ACP’s learned meta-router beats the best static single-agent policy on cost-normalized reward, routes security fixes to the more reliable harness, routes ordinary bugfixes to the cheaper harness, escalates high-uncertainty tasks to parallel/advisor topologies only when worth the cost, and refuses to learn from contaminated attempts.

That would be genuinely differentiated. It would show ACP as a **measurement-trustworthy, memory-using, complexity-aware meta-agent**, not just a wrapper around coding agents.






-----------




# RESEARCH DIRECTIONS, NOT YET FACTORING IN MEMORY/CONTEXT PAPERS FULLY

Yes. I’d shortlist **10 implementation directions**, grouped by priority.

## Tier 1 — implement next

### 1. **Layered advisor / metacognitive escalation**

Implement a cheap executor that can consult a stronger read-only advisor only when confidence drops. This combines the Harvey-style advisor pattern with MetaCogAgent’s confidence-driven delegation and Conductor’s learned orchestration idea. MetaCogAgent explicitly routes low-confidence tasks to delegation; Conductor trains a small orchestrator to design topology and targeted prompts for worker agents. ([GitHub][1]) ([GitHub][1])

**ACP module:**

```text
AdvisorPolicy
AdvisorCall
consult_advisor tool
advisor_budget
advisor_trace
advisor OPE/cost report
```

---

### 2. **Weak-model candidate generation + verifier/comparator**

Shortlist this immediately. Weak-Model Critic-Comparator shows cheap models can match frontier SWE-bench performance by sampling k candidates and selecting via execution/proof signals instead of self-ranking. ([GitHub][1])

**ACP module:**

```text
CandidateSampler
ExecutionComparator
ProofSignalSelector
BestOfKPolicy
cost_per_verified_success
```

This is directly useful for coding agents.

---

### 3. **AutoTTS-style controller search for topology**

ACP already has topology actions. AutoTTS reframes test-time scaling as controller synthesis over pre-collected traces, so strategies can be searched offline instead of hand-tuned. ([GitHub][1])

**ACP module:**

```text
TopologyControllerSearch
offline_trace_controller_eval
skip/retry/branch/verify policy search
```

This should optimize when to branch, verify, ask advisor, or stop.

---

### 4. **Meta-Harness / Life-Harness style harness optimization**

SkillOpt optimizes skills. Next, optimize **harness code and interfaces**. Meta-Harness automatically searches over harness code using prior scores and execution traces, while Code as Agent Harness argues harnesses should be executable, inspectable, stateful, and governed. ([GitHub][1]) ([GitHub][1])

**ACP module:**

```text
HarnessPatchProposal
HarnessCandidate
HarnessRegressionSuite
HarnessCanary
HarnessRollback
```

This is the natural extension beyond skill docs.

---

### 5. **Synthetic task-corpus generator / active benchmark builder**

General-Agent builds a self-evolving synthetic task corpus with difficulty calibration. ACP needs this to grow capability-matrix cells cheaply. ([GitHub][1])

**ACP module:**

```text
TaskSynthesizer
DifficultyBandFilter
CapabilityGapGenerator
SyntheticTaskAcceptanceGate
```

Use it to populate sparse routing/skill cells.

---

## Tier 2 — important, after the next sprint

### 6. **Context-strategy optimizer: grep vs embeddings + deployment-aware context**

“Is Grep All You Need?” argues grep can match or beat embeddings in coding-agent tasks when the harness is right. The Efficiency Frontier argues context strategy should be chosen by cost/performance/reuse regime. ([GitHub][1]) ([GitHub][2])

**ACP module:**

```text
ContextStrategyOPE
grep_vs_embedding_bakeoff
reuse_aware_context_cost_model
```

Do not default to vector DB.

---

### 7. **Memory lifecycle / aging benchmark**

MeMo treats memory as a learned subsystem with read/write/integrate interfaces, while AgingBench frames long-lived agent degradation as compression/interference/revision/maintenance aging. ([GitHub][1]) ([GitHub][2])

**ACP module:**

```text
MemoryPolicy
MemoryAgingBenchmark
MemoryRevisionAudit
MemoryPoisoningDetector
```

This matters once ACP runs over weeks/months.

---

### 8. **Stochastic–deterministic boundary formalization**

Production Agent Architecture Methodology introduces the stochastic-deterministic boundary: proposer, verifier, commit, reject. ACP already has this implicitly; make it explicit. ([GitHub][1])

**ACP module:**

```text
SDBContract
ProposeVerifyCommitReject
DeterministicCommitGate
```

This improves auditability and safety.

---

### 9. **Selective abstention / “sufficient context” gates**

Selective RAG work shows models often hallucinate even with sufficient context and need answer/abstain gates; this maps to ACP viability and measurement quality. ([GitHub][3])

**ACP module:**

```text
ContextSufficiencyJudge
AnswerOrAbstainGate
SpecNeededGate
```

Especially useful for vague tickets.

---

### 10. **Workflow distillation / agentless training**

Kimi-Dev and workflow-distillation-style work suggest coding workflow priors can be trained into smaller models after enough traces. Kimi-Dev reports agentless training as a software-engineering prior and trajectory fine-tuning improving SWE-Agent-like performance. ([GitHub][3])

**ACP module:**

```text
TraceDistillationDataset
WorkflowPriorTrainer
small_model_router_or_repair_model
```

This is later than SkillOpt, but important.

---

## Tier 3 — researchy, but worth tracking

### 11. **HeavySkill / internalized parallel-deliberation skill**

HeavySkill says the useful harness may boil down to an inner skill: parallel reasoning followed by deliberation, portable across harnesses and trainable. ([GitHub][1])

Use it as a SkillOpt target:

```text
parallel_attempt_skill
deliberate_then_commit_skill
```

---

### 12. **Tool-use RL / format-adherence training**

Tool-N1 trains tool use with binary functional/format rewards rather than SFT trajectories. This maps to ACP’s HAR/HFR/PWL and vendor harness tool-call format failures. ([GitHub][3])

Use for:

```text
tool_call_format_model
harness_activation_finetune
```

---

### 13. **DGM / open-ended self-improving agents**

Darwin Gödel Machine modifies its own codebase and keeps successful variants in an archive. Useful, but dangerous. ACP should only adopt it behind harness-update PRs, sandboxing, and canaries. ([GitHub][3])

Use for:

```text
HarnessCodeEvolutionArchive
```

---

### 14. **DeepConf / confidence-based trace pruning**

Deep Think with Confidence uses intrinsic confidence to prune reasoning paths and save tokens. ([GitHub][3])

Use for:

```text
candidate_pruning
advisor_trigger
early_stop_policy
```

---

### 15. **Agent benchmark hardening: NanoGPT-Bench / rebuild-a-breakthrough**

NanoGPT-Bench and Connect Four AlphaZero-style tasks test real research-engineering loops instead of patch-only fixes. ([GitHub][2]) ([GitHub][1])

Use for ACP’s hard eval suite.

---

## My recommended implementation order

```text
1. AdvisorPolicy / consult_advisor
2. Weak-model k-candidate + verifier/comparator
3. AutoTTS-style topology controller search
4. Vendor-native harness live gate + skill injection
5. Synthetic task generator for sparse capability cells
6. Context strategy optimizer: grep vs embeddings vs hybrid
7. SkillOpt v2: multi-skill transfer + negative-transfer + composition
8. Memory lifecycle / aging benchmark
9. SDB formalization
10. Workflow distillation / local small-model training
```

## What to skip for now

Do not prioritize:

```text
pretraining methods
mechanistic neuron/circuit interventions
scientific forecasting benchmarks
general math discovery systems
large-scale RL training
```

They are interesting, but ACP’s near-term moat is **routing, measurement trust, harness/skill optimization, live vendor proof, and cheap-frontier hybrid execution**.

[1]: https://raw.githubusercontent.com/dair-ai/AI-Papers-of-the-Week/main/years/2026.md "raw.githubusercontent.com"
[2]: https://github.com/dair-ai/AI-Papers-of-the-Week/blob/main/years/2026.md "AI-Papers-of-the-Week/years/2026.md at main · dair-ai/AI-Papers-of-the-Week · GitHub"
[3]: https://raw.githubusercontent.com/dair-ai/AI-Papers-of-the-Week/main/years/2025.md "raw.githubusercontent.com"
