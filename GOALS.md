Below is the next set of instructions to build a compelling, differentiated and groundbreaking meta-agent that is truly at the leading edge and can route/delegate to other agents based on task complexity, context, etc. Lower down you'll see some research directions; some of this is implemented, and you can also look as needed at the papers on agent harnesses and context/memory in the pdfs directory, that's fine too. We should above all make sure that we're data driven -look at the evals we just did and which are recorded in the repos. If they help, great; if not, come up with more challenging and realistic live/unseen evals. In particular we haven't done much, I think, on memory and context optimization.

---------------------------------------------------

Below is the plan I’d give the coding agent next. The current baseline is strong: Alpha 42 delivered the MetaRouter Arena, AdvisorPolicy, best-of-k comparator, topology-controller search, ContextStrategyOPE, sufficiency/abstention gates, FinOps reports, vendor-native availability gates, memory/aging smoke, and a green suite at **1235 passed / 18 skipped / 0 failed**. The live Alpha 42 signal is also meaningful: `repo_map_router` is the best routable policy, advisor escalation improved verified success, topology search found a modest gain, memory improved first-attempt success, and best-of-k was honest/null on quality at the current `k=2`. 

## North star for the next phase

Move from **“we built a promising metarouter substrate”** to:

> ACP is a production-grade, evidence-driven coding-agent meta-control-plane that continuously evaluates agents, context strategies, memory, topology, verification depth, and budget allocation; routes work above Claude/Codex/OpenAI/Gemini/OpenHands-style agents; and proves lower cost per verified success than static single-agent policies on live, unseen, hidden-tested tasks.

OpenAI/Gemini should remain **adapter hooks + mocked contract tests only** in this environment. Do not block any gate on live OpenAI/Gemini access. Live proof should use reachable Claude, deterministic baselines, and any locally available Codex/OpenHands hooks.

## The next program: Alpha 43–48

I’d plan this as a six-sprint arc, not one narrow sprint.

```text
Alpha 43 — Scale the MetaRouter Arena to real external validity
Alpha 44 — Decision-quality controller: advisor, best-of-k, topology, abstention
Alpha 45 — Context + memory as a learned subsystem
Alpha 46 — Agent FinOps + provider marketplace
Alpha 47 — Production deployment, isolation, queues, observability
Alpha 48 — Hard research-engineering benchmark suite
```

The immediate next sprint should be **Alpha 43**, but the coding agent should scaffold interfaces with Alpha 44–48 in mind.

---

# Alpha 43 — Scale-Proven MetaRouter Arena

## Mission

Take the Alpha 42 arena from smoke-scale proof to a statistically useful, hidden-tested, replayable evaluation corpus. Alpha 42 proved the shape; Alpha 43 should prove robustness.

Alpha 42’s strongest result was that `repo_map_router` beat static baselines on both verified success and cost in the live arena, but the report itself notes the evidence is smoke-scale and the ≥300-cell live gate still needs a larger budget.  The next sprint should close that exact gap.

## P0 — Expand MetaRouter Arena to ≥300 conclusive cells

### Implement

```text
evals/metarouter_arena/scaled_runner.py
evals/metarouter_arena/task_loader.py
evals/metarouter_arena/replication.py
evals/metarouter_arena/cell_accounting.py
evals/metarouter_arena/statistics.py
```

### Add task sources

```text
1. Existing synthetic-but-realistic arena tasks
2. Frozen local repo fixtures
3. GitHub issue replay bundles, offline where network is absent
4. Mutation/adversarial patch tasks
5. Cross-file context tasks
6. Underspecified ticket tasks
7. Security remediation tasks
8. CI/migration breakage tasks
9. Memory-required repeated-failure tasks
10. Research-engineering tasks
```

### Required policy matrix

```text
cheap_single
claude_harness
repo_map_router
advisor_router
best_of_k_router
topology_controller
memory_router
abstain_router
oracle_upper_bound
static_cost_saver
static_success_max
```

### Required context matrix

```text
none
grep
repo_map
hybrid_keyword_embedding
repo_map_plus_grep
repo_map_plus_memory
memory_negative_prior
```

### Required artifacts

```text
reports/metarouter_arena_scaled.json
reports/metarouter_arena_scaled.md
reports/metarouter_cell_accounting.json
reports/metarouter_confidence_intervals.json
reports/metarouter_failure_taxonomy.json
```

### Acceptance gate

```text
- >=300 conclusive cells.
- >=50 tasks.
- >=8 task types.
- >=5 context-need classes.
- conclusive rate >=80%.
- high-risk false auto-approve = 0.
- no contaminated sample updates capability/OPE/promotion.
- every headline claim maps to a fresh artifact.
```

### Promotion rule

A policy can be promoted only if it beats current router on at least one of:

```text
verified_success_rate at same/lower cost
cost_per_verified_success at same/higher success
high-risk false-auto-approve reduction
human-review reduction with no quality loss
latency reduction with no quality loss
```

---

# P1 — Real GitHub Issue Replay, but frozen/offline-first

Round 28 previously identified real GitHub issue ingestion as a remaining gap; the repo had offline components but not full live-history ingest.  Alpha 43 should make issue replay a first-class evaluation source.

## Implement

```text
evals/issue_replay/
  ingest.py
  freeze.py
  replay_task.py
  gold_patch.py
  hidden_tests.py
  patch_equivalence.py
  report.py
```

## Data model

```text
IssueReplayTask:
  repo_url
  repo_name
  base_sha
  issue_url
  issue_title
  issue_body
  fixing_pr_url
  fixing_pr_sha
  gold_patch_hash
  public_test_command
  hidden_test_command
  task_type
  risk_level
  difficulty_band
  context_need
  leakage_notes
```

## Modes

```text
online_ingest:
  fetch GitHub issues/PRs when network/auth exists

offline_freeze:
  consume pre-frozen task bundles committed under evals/tasks/

replay_only:
  never contacts network; runs agents on frozen tasks
```

## Acceptance

```text
- At least 20 frozen issue-replay tasks.
- No gold patch in agent-visible prompt.
- Public tests fail at base_sha.
- Gold fix passes public + hidden verification.
- Agent solution judged by hidden tests + patch-equivalence judge.
- Artifact clearly labels source as real_issue_replay, synthetic, or fixture.
```

---

# P2 — AdvisorPolicy v2: confidence calibration and read-only critique

Alpha 42 proved advisor escalation can help: the sprint report says advisor routing delivered a +0.20 verified-success lift.  Now turn advisor use from “helpful heuristic” into a calibrated decision.

## Implement

```text
src/acp/routing/advisor_calibration.py
src/acp/evaluation/advisor_counterfactuals.py
src/acp/evaluation/advisor_trigger_quality.py
src/acp/finops/advisor_marginal_value.py
```

## Advisor trigger features

```text
first_attempt_failed
no_tests_run
tests_failed
hidden_verifier_uncertain
diff_too_broad
context_sufficiency_low
retrieval_entropy_high
cheap_policy_low_success_bucket
high_risk_task
underspecified_ticket
memory_negative_prior_hit
```

## Advisor modes

```text
read_only_strategy_advice
read_only_file_selection
read_only_test_plan
read_only_patch_critique
second_opinion_before_auto_approve
```

## Hard rules

```text
- Advisor cannot edit files.
- Advisor cannot override deterministic verifier failure.
- Advisor recommendation is evidence, not authority.
- Advisor calls are budgeted.
- Advisor use must be justified in policy dossier.
```

## Acceptance

```text
- Advisor calls only when expected marginal value is positive.
- Advisor reduces false auto-approve or improves success on at least one bucket.
- Advisor does not regress cost_per_verified_success by >10% globally.
- Advisor no-op/low-value calls are flagged as waste.
```

---

# P3 — Best-of-k v2: diversity, pruning, and comparator strength

Alpha 42’s best-of-k was honest: it beat the strong harness on cost but did not improve quality at `k=2`.  That is useful signal. The next step is not to abandon best-of-k, but to make it **diverse and proof-selected**.

## Implement

```text
src/acp/routing/candidate_diversity.py
src/acp/routing/candidate_pruning.py
src/acp/evaluation/comparator_strength.py
src/acp/evaluation/candidate_failure_taxonomy.py
```

## Candidate diversity strategies

```text
same_model_different_context
same_model_different_prompt
repo_map_vs_grep_context
cheap_model_then_strong_repair
test_first_candidate
minimal_patch_candidate
security_hardened_candidate
```

## Comparator signals

```text
public_tests
hidden_tests
semantic_patch_equivalence
diff_minimality
forbidden_file_touch
test_gaming_detector
security_detector
post_merge_risk_score
```

## Acceptance

```text
- k=3 and k=5 tested separately.
- Early stopping saves cost when first candidate is verified.
- Candidate diversity improves success over naive same-prompt k.
- Comparator rejects public-pass/hidden-fail patches.
- Report includes best_of_k_waste_rate and marginal value of each extra candidate.
```

## Artifact

```text
reports/best_of_k_v2.json
reports/candidate_diversity_ablation.json
reports/proof_signal_selector_strength.json
```

---

# P4 — TopologyController v2: executable learned programs

Alpha 42 added topology search and found a +0.08 gain.  Now make topology choices more than labels: execute a learned controller program over real workflow states.

## Implement

```text
src/acp/routing/topology_program_executor.py
src/acp/routing/controller_policy_store.py
src/acp/routing/controller_safety_rules.py
src/acp/evaluation/controller_ablation.py
```

## Controller actions

```text
start_cheap
start_strong
ask_advisor
retry_with_repo_map
retry_with_grep
retry_with_memory
sample_k_candidates
branch_parallel
run_strict_verifier
route_to_human
abstain
commit_success
terminate_failure
```

## Safety invariants

```text
- high-risk task cannot skip strict verifier.
- public-test-only success cannot auto-approve security tasks.
- branch_parallel uses isolated workspaces.
- all losing branches are persisted as training examples.
- controller cannot spend beyond budget class.
```

## Acceptance

```text
- Offline replay predicts controller value on heldout traces.
- Live arena confirms no major distribution mismatch.
- Controller beats current router or refuses promotion.
- Policy dossier includes controller program and why-not actions.
```

---

# P5 — ContextStrategyOPE v2: repo_map, grep, embeddings, memory

The repo-map work is now one of ACP’s strongest differentiators. A previous sprint implemented Aider-style repo-map, showed **21× API coverage per token**, and reproduced a live cross-file lift from **0/3 to 3/3**.  Alpha 42 then integrated ContextStrategyOPE and routed cross-file/broad-repo tasks toward repo_map. 

Now build the scientific context benchmark.

## Implement

```text
src/acp/context/context_bandit.py
src/acp/context/context_ablation_runner.py
src/acp/context/context_reuse_model.py
src/acp/context/context_token_economics.py
```

## Benchmarks

```text
exact_symbol:
  grep should often win

cross_file_api:
  repo_map should often win

broad_architecture:
  repo_map_plus_hybrid may win

local_bug:
  small grep/context pack should win

memory_required:
  repo_map_plus_memory should win

generated/noisy repo:
  embeddings may degrade; grep/repo_map should be tested

large repo:
  measure latency + token pressure
```

## Metrics

```text
API coverage per token
definition recall@k
callsite recall@k
context token cost
context build latency
success rate downstream
cost_per_verified_success
secret leakage
decoy false-positive rate
```

## Acceptance

```text
- repo_map win replicated in >=3 task families.
- grep beats repo_map/embedding on at least one exact-symbol bucket, or null is reported.
- embeddings are not default unless evidence supports them.
- context strategy is routed by OPE, not hardcoded.
```

---

# P6 — Memory v2: write, retrieve, revise, forget

Alpha 42 added memory and an aging smoke benchmark, with a reported first-attempt lift around +0.17.  Now turn memory into a governed subsystem.

## Implement

```text
src/acp/memory/experience_store.py
src/acp/memory/memory_retriever.py
src/acp/memory/memory_revision.py
src/acp/memory/memory_decay.py
src/acp/memory/memory_poisoning.py
src/acp/memory/memory_privacy.py
```

## Memory records

```text
ExperienceEpisode:
  repo_family
  repo_id
  task_type
  failure_signature
  context_need
  context_strategy
  agent
  topology
  advisor_used
  changed_symbols
  tests_run
  verifier_outcome
  human_review_outcome
  post_merge_outcome
  reward
  cost
  privacy_scope
  trust_score
  created_at
  decay_score
```

## Policies

```text
write_only_conclusive
write_negative_memory
do_not_repeat_failed_strategy
retrieve_same_repo
retrieve_repo_family
retrieve_failure_signature
forget_stale_memory
revise_after_post_merge_failure
quarantine_poisoned_memory
```

## Acceptance

```text
- Memory improves cost_per_verified_success on repeated-pattern tasks.
- Negative memory prevents repeating known bad strategies.
- Stale memory decays.
- Post-merge reverts revise memory.
- Cross-tenant/private memory never leaks.
- Memory poisoning attempts are quarantined.
```

## Artifact

```text
reports/memory_v2_ablation.json
reports/memory_privacy_redteam.json
reports/memory_revision_audit.json
reports/memory_aging_v2.json
```

---

# P7 — Agent FinOps v2: budget optimization as product surface

FinOps is now not just logging cost. It should become a routing objective.

## Implement

```text
src/acp/finops/provider_market.py
src/acp/finops/compute_allocation.py
src/acp/finops/marginal_value_controller.py
src/acp/finops/cost_anomaly.py
src/acp/finops/savings_recommendations.py
```

## Reports

```text
reports/finops_provider_market.json
reports/finops_marginal_value.json
reports/finops_budget_policy.json
reports/finops_cost_anomalies.json
```

## Metrics

```text
cost_per_verified_success
cost_per_conclusive_cell
cost_per_hidden_test_pass
advisor_cost_share
best_of_k_waste
context_token_cost
verification_cost
human_review_cost_proxy
latency_cost_tradeoff
provider_unavailability_cost
```

## Budget classes

```text
docs_low_risk
ordinary_bugfix
cross_file_bugfix
security_fix
migration
incident
research_engineering
```

## Acceptance

```text
- Docs tasks cannot trigger expensive topologies without evidence.
- Security tasks can spend more but require strict verifier.
- Marginal-value controller stops best-of-k when expected value is negative.
- FinOps report recommends concrete policy changes.
- Provider unavailable != provider failed.
```

---

# P8 — Vendor/provider abstraction v2: hooks for OpenAI/Gemini, no live gate

The previous P1–P5 work made real adapters discoverable, with unavailable reasons, and ensured missing providers are not treated as capability failures.  Alpha 43 should complete the provider abstraction.

## Implement

```text
src/acp/providers/base.py
src/acp/providers/anthropic.py
src/acp/providers/openai.py
src/acp/providers/gemini.py
src/acp/providers/codex.py
src/acp/providers/openhands.py
src/acp/providers/health.py
src/acp/providers/contracts.py
```

## Contract tests

```text
tests/contracts/test_provider_contract.py
tests/contracts/test_openai_provider_contract.py
tests/contracts/test_gemini_provider_contract.py
tests/contracts/test_claude_provider_contract.py
tests/contracts/test_codex_provider_contract.py
```

## Required contract

```text
health reports available/unavailable/degraded
unavailable has actionable reason
provider failure becomes infra/inconclusive
provider absence never updates capability matrix
trace schema normalized
cost model present or explicitly unknown
budget/retry policy declared
SDK/network calls mocked in unit tests
```

## Acceptance

```text
- OpenAI/Gemini hooks exist.
- OpenAI/Gemini live tests are optional/self-skipping.
- Mocked OpenAI/Gemini contract tests pass.
- `acp provider health` explains all providers.
- no routing claim ranks a provider without conclusive live cells.
```

---

# P9 — Production-ish deployment gate

The project has made strong progress on Docker/Kubernetes and governance, but the previous reports still note that full production-ish infra was not stood up in the local environment.  Alpha 43 or 44 should turn this into a hard gate.

## Implement

```text
deploy/local-prod/
  docker-compose.yml
  kind-or-k3d-cluster.yaml
  postgres
  minio
  redis-or-queue
  worker
  api
  sandbox-runner

src/acp/deploy/health_gates.py
src/acp/deploy/worker_queue.py
src/acp/deploy/artifact_store.py
```

## Acceptance

```text
- API schedules; worker executes.
- Postgres stores entities.
- Object store stores artifacts.
- Sandbox has no host secret leakage.
- NetworkPolicy enforcement tested when CNI supports it.
- 100 concurrent jobs complete.
- no duplicate run IDs.
- no orphan workspaces/pods.
- p95 latency reported.
- health fails if deployment artifact stale.
```

## Artifact

```text
reports/productionish_deploy_gate.json
reports/concurrent_worker_soak.json
reports/sandbox_network_policy_live.json
```

---

# P10 — Human/operator learning loop

Alpha 42 has the metarouter substrate; now build the operator feedback product loop.

## Implement

```text
src/acp/review/operator_metrics.py
src/acp/review/label_quality.py
src/acp/review/active_learning_queue.py
src/acp/review/policy_update_from_labels.py
```

## Metrics

```text
reviewer_agreement
label_latency
override_rate
false_auto_approve_near_miss
policy_changed_after_label
task_bucket_uncertainty
human_review_cost_proxy
```

## Acceptance

```text
- Active learner selects highest-value review items.
- Human labels change future routing decisions in replay.
- Disagreement blocks learning.
- High-risk labels remain advisory until governance gates pass.
- Operator inbox shows why item matters.
```

---

# P11 — Hard benchmark suite: beyond patch tasks

To be groundbreaking, ACP needs harder tasks than small bugfixes.

## Build benchmark families

```text
1. Cross-file API discovery
2. Security remediation
3. CI/migration breakage
4. Flaky test diagnosis
5. Performance regression
6. Large-repo orientation
7. Multi-step feature implementation
8. Refactor with behavior preservation
9. Underspecified ticket requiring abstention/spec request
10. Research-engineering task
```

## Research-engineering tasks

```text
nanogpt-style training loop fix
small interpreter/compiler bug
mini database query planner bug
connect-four/alpha-zero-style self-play bug
benchmark reproduction task
multi-file algorithmic optimization
```

## Acceptance

```text
- Tasks cannot be solved by public tests alone.
- Hidden tests or semantic judge required.
- At least one static strong-agent baseline fails per family.
- MetaRouter must show either better cost or better success.
```

---

# P12 — Harness evolution as guarded PRs

The prior work already has harness-evolution scaffolding and guarded PR machinery; next make it close the loop from failures to proposed harness patches. 

## Implement

```text
src/acp/training/harness_failure_clusters.py
src/acp/training/harness_patch_author.py
src/acp/training/harness_canary_runner.py
src/acp/training/harness_pr_pipeline.py
```

## Flow

```text
failed conclusive traces
  -> cluster failure mode
  -> propose harness patch
  -> run static/security scan
  -> run regression suite
  -> run negative-transfer suite
  -> run canary
  -> open guarded PR
  -> rollback metadata
```

## Patch types

```text
tool schema
finish discipline
test-running discipline
advisor trigger
repo_map formatting
grep result formatting
memory snippet formatting
budget policy
nudge wording
```

## Acceptance

```text
- At least 3 proposals generated from real failure clusters.
- At least 1 rejected for negative transfer.
- At least 1 rejected for no measured lift.
- Promotion only through guarded PR.
- No protected branch writes.
```

---

# P13 — Claim checker and evidence freshness

The P1–P5 work fixed stale claims once; Alpha 43 should make this impossible by construction. 

## Implement

```text
src/acp/reports/claim_registry.py
src/acp/reports/evidence_freshness.py
src/acp/reports/claim_checker.py
```

## Claim mapping

```text
"repo_map improves cross-file tasks"
  requires fresh repo_map_ab artifact

"advisor improves success"
  requires fresh advisor_ope artifact

"production ready"
  requires fresh production health + sandbox + provider + artifact gates

"provider X is best for task Y"
  requires enough conclusive live cells for provider X/task Y
```

## Acceptance

```text
- docs test fails if a claim lacks artifact.
- contaminated artifact blocks claim.
- stale artifact blocks claim.
- fixture-only artifact cannot support live claim.
- generated docs include claim -> evidence map.
```

---

# Alpha 43 definition of done

The coding agent should not declare Alpha 43 done until these commands exist and pass:

```bash
uv run acp arena run-scaled \
  --tasks 50 \
  --target-conclusive-cells 300 \
  --policies current,repo_map,advisor,best_of_k,topology_controller,memory,abstain \
  --context-strategies grep,repo_map,hybrid,repo_map_plus_memory \
  --hidden-tests \
  --persist

uv run acp arena compare --from latest-scaled
uv run acp finops report --from latest-scaled
uv run acp context strategy-ope --from latest-scaled
uv run acp memory report --from latest-scaled
uv run acp provider health --show-unavailable
uv run acp reports claim-check
uv run acp health --mode production
```

Required committed artifacts:

```text
reports/metarouter_arena_scaled.json
reports/metarouter_policy_compare_scaled.json
reports/finops_marginal_value.json
reports/context_strategy_ope_v2.json
reports/memory_v2_ablation.json
reports/advisor_calibration.json
reports/best_of_k_v2.json
reports/topology_controller_v2.json
reports/provider_contract_gate.json
reports/claim_evidence_map.json
reports/alpha43_report.md
```

Minimum pass criteria:

```text
- >=300 conclusive cells.
- conclusive rate >=80%.
- high-risk false auto-approve = 0.
- at least one learned/routed policy beats current router or current router is confirmed best.
- repo_map replicated across >=3 task families or claim downgraded.
- advisor escalation has positive marginal value in at least one bucket or is demoted.
- best-of-k v2 either shows positive marginal value or is restricted to buckets where it helps.
- memory improves repeated-pattern tasks or remains advisory.
- no OpenAI/Gemini live claim without live evidence.
- provider unavailability is reported, not counted as capability failure.
- docs claim checker passes.
```

## Instruction block to give the coding agent

```text
Implement Alpha 43: Scale-Proven MetaRouter + Evidence Freshness.

Use Alpha 42 as the baseline. Do not rebuild already-delivered modules unless needed. Your job is to scale, harden, and prove.

Priorities:
1. Scale MetaRouter Arena to >=300 conclusive cells across >=50 tasks.
2. Add real/frozen GitHub issue replay bundles.
3. Build AdvisorPolicy v2 with calibrated marginal-value triggers.
4. Build best-of-k v2 with diversity and proof-based comparator.
5. Build executable TopologyController v2.
6. Upgrade ContextStrategyOPE with repo_map/grep/hybrid/memory ablations.
7. Upgrade Memory v2 with revision, decay, negative memory, poisoning defense.
8. Build Agent FinOps v2: marginal value of compute and provider-market reports.
9. Complete provider contracts for Claude/OpenAI/Gemini/Codex/OpenHands; OpenAI/Gemini mocked only here.
10. Build claim checker so docs cannot overclaim stale/contaminated evidence.

Hard rules:
- Unavailable provider != failed provider.
- No contaminated sample enters capability/OPE/promotion.
- No hidden-test failure can auto-approve.
- No high-risk task can skip strict verification.
- No live claim from fixture-only evidence.
- Every policy promotion must beat a static baseline with confidence intervals or remain advisory.

Produce:
reports/alpha43_report.md
reports/metarouter_arena_scaled.json
reports/finops_marginal_value.json
reports/context_strategy_ope_v2.json
reports/memory_v2_ablation.json
reports/provider_contract_gate.json
reports/claim_evidence_map.json

Finish only when the full suite, ruff, mypy, alembic, reports validate, and claim-check are green.
```

## What to deprioritize

Do not spend Alpha 43 on:

```text
- more dashboards without routing decisions
- more synthetic-only wins
- OpenAI/Gemini live testing in this environment
- large-scale RL
- LoRA unless hardware and a narrow target exist
- new adapters that do not emit normalized traces
- model self-ranking without verifier/comparator signals
- marketing claims not backed by fresh artifacts
```

## Strategic summary

Alpha 42 showed ACP can be a real metarouter. Alpha 43 should make that claim hard to dismiss:

```text
from smoke proof -> scaled evidence
from feature modules -> policy promotion gates
from context trick -> learned context/memory subsystem
from cost logging -> FinOps controller
from adapter list -> provider marketplace
from reports -> claim-checked evidence
```

The winning product story becomes:

> ACP sits above Claude, Codex, OpenAI, Gemini, OpenHands, and future agents. It learns which agent, context, memory, topology, advisor, verifier depth, and budget to use for each coding task. It proves decisions with hidden tests, conclusive measurement, and cost-per-verified-success — and it refuses to overclaim when evidence is stale, unavailable, or contaminated.
