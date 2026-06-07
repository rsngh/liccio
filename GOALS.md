Below is the next set of instructions to build a compelling, differentiated and groundbreaking meta-agent that is truly at the leading edge and can route/delegate to other agents based on task complexity, context, etc. Lower down you'll see some research directions; some of this is implemented, and you can also look as needed at the papers on agent harnesses and context/memory in the pdfs directory, that's fine too. We should above all make sure that we're data driven -look at the evals we just did and which are recorded in the repos. If they help, great; if not, come up with more challenging and realistic live/unseen evals. In particular we haven't done much, I think, on memory and context optimization.

----------------------------------------------

According to a document from June 7, 2026, the branch is now at a substantially stronger baseline than the last pass: `CURRENT_STATUS.md` reports **1265 passing / 18 skipped**, `ruff` and `mypy` clean across **324 source files**, and the branch labels this as **Alpha 43 Scale-Proven MetaRouter** on top of the repo-map and Alpha 42 metarouter work.  The key Alpha 43 result is not “we found a magic router”; it is better: the system ran **53 unseen, hidden-tested tasks × 6 policies = 318 conclusive cells**, 100% conclusive, with Wilson confidence intervals and a claim checker tying claims to fresh, uncontaminated evidence. 

My read: **Alpha 43 changed the problem.** ACP no longer needs more smoke demos. It now needs harder, more realistic tasks that break the current ceiling, plus executable orchestration at scale. The honest Alpha 43 finding is that `grep_router`, `repo_map_router`, and `abstain_router` have excellent point estimates, but none beats `cheap_single` with CI separation because Sonnet 4.6 solves most current arena tasks from minimal context.  That means the next round should not be “scale the same arena again.” It should be **hard-realism, executable topology, memory longevity, and FinOps under meaningful uncertainty**.

## Executive recommendation

Make the next sprint:

# **Alpha 44 — Hard-Realism MetaRouter: Executable Orchestration, Long-Lived Memory, and FinOps Under Uncertainty**

The acceptance question should be:

> Can ACP beat a strong cheap single-agent baseline on hard, realistic, hidden-tested tasks by deciding when to use grep, repo-map, memory, advisor calls, best-of-k, branch-parallel execution, strict verification, abstention, and human/operator review — while optimizing cost per verified success?

The core thesis should shift from **“Can metarouting work?”** to **“When does metarouting become necessary?”** Alpha 43 shows easy/medium tasks are near-ceiling; Alpha 44 should design the workloads where a true control plane has differentiated value.

## What the latest evals say

The strongest signal is that **cheap context strategies are winning**. In Alpha 43, `grep_router` had the best point estimate: **0.981 verified success**, **$0.001361 per verified success**, while `repo_map_router` hit **0.962** at **$0.0015**. The incumbent `cheap_single` reached **0.887** at **$0.001578**. 

The most important negative signal is the confidence interval result: despite better point estimates, **no policy was promotable with confidence** versus the incumbent.  The report explicitly attributes this to a **ceiling effect**: Sonnet 4.6 solved most tasks from minimal context, compressing the room for metarouting to prove value. 

The context result is also sobering: `context_strategy_ope_v2` recommends `grep` for most measured buckets, has **no samples** for `broad_repo_map`, and marks grep-vs-embedding as **insufficient evidence** because there were zero embedding samples.   This is consistent with the recent “Is Grep All You Need?” result, which found grep often outperformed vector retrieval across several harnesses while emphasizing that harness/tool style strongly affects results. ([arXiv][1])

Memory is the most promising differentiated subsystem after context. Alpha 43’s memory ablation solved **25/30** sessions vs **11/30** baseline and cut cost per verified success from **$0.007909** to **$0.00344**.  That is a real moat candidate: a metarouter can get better over time, whereas a bare coding agent does not.

FinOps is now present but still shallow. The current FinOps artifact proceeds on repo-map context, advisor, and extra best-of-k while expected marginal value is positive; that is the right control surface, but it needs to be learned from harder tasks and provider availability, not just static assumptions. 

Provider abstraction is correctly honest: the provider contract gate passes for Anthropic/OpenAI/Gemini/Codex/OpenHands, but OpenAI/Gemini are contract-tested hooks without network, and unavailable providers are infra-not-capability.   Keep that discipline. Do not try to force OpenAI/Gemini live proof in this environment.

## Alpha 44 priorities

### P0 — Build a Hard-Realism Arena that defeats the ceiling effect

Alpha 43 proved the arena mechanics. Alpha 44 must make the tasks harder and more realistic.

Implement:

```text
evals/hard_realism_arena/
  schema.py
  task_pack.py
  run.py
  hidden_verifiers.py
  issue_replay.py
  research_engineering.py
  failure_taxonomy.py
  report.py
```

Task families:

```text
1. Real GitHub issue replay bundles
2. Multi-file cross-module bugfixes
3. Security remediation with hidden exploit tests
4. CI/migration failures
5. Performance regression fixes
6. Flaky test diagnosis
7. Underspecified tickets requiring spec-needed/abstain
8. Long-lived memory tasks with changed repo conventions
9. Research-engineering tasks
10. Harness-failure tasks where tool use discipline matters
```

Each task should have:

```text
public tests
hidden tests
forbidden-file rules
semantic patch judge
diff minimality check
test-gaming detector
context-need label
risk level
expected blast radius
budget class
```

Acceptance gate:

```text
- >=100 hard tasks
- >=600 conclusive cells
- >=10 task families
- high-risk false auto-approve = 0
- at least 25 tasks where cheap_single fails
- at least 25 tasks where context strategy materially changes outcome
- at least 20 tasks where memory/advisor/topology can matter
- no policy promotion without CI separation or a clearly scoped bucket-level promotion
```

Key report:

```text
reports/hard_realism_arena.json
reports/hard_realism_policy_compare.json
reports/hard_realism_failure_taxonomy.json
```

Promotion should be bucketed. A global policy may still fail to beat `cheap_single`, but ACP should be able to say:

```text
for security_fix + high_risk: strict_verify + advisor wins
for cross_file_api: grep/repo_map wins
for repeated failure_signature: memory wins
for underspecified: abstain/spec-needed wins
for performance: branch_parallel or advisor wins
```

### P1 — Real GitHub issue replay bundles, offline-first

This is the highest-value deferred item from Alpha 43. The report explicitly lists real GitHub issue-replay bundles as deferred. 

Implement:

```text
evals/issue_replay/
  ingest_github.py
  freeze_bundle.py
  replay_runner.py
  gold_patch.py
  hidden_test_builder.py
  patch_equivalence.py
```

Bundle format:

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
  context_need
  difficulty_band
  leakage_notes
```

Modes:

```text
online_ingest       # only when network/auth is present
offline_freeze      # build committed bundles
replay_only         # no network; run frozen tasks
```

Acceptance:

```text
- 30 frozen real issue-replay tasks
- no gold patch visible to the agent
- public tests fail at base_sha
- gold fix passes public + hidden tests
- agent output judged by hidden tests + semantic patch equivalence
- issue replay is clearly separated from synthetic fixtures in reports
```

This will make ACP’s benchmark feel like a real coding-agent metarouter benchmark, not an internally generated puzzle set.

### P2 — Executable topology controller live

Alpha 43 delivered topology-controller search, but the report says the executable topology controller live work was deferred.  AutoTTS is relevant here because it frames test-time scaling as controller synthesis over traces, deciding when to branch, continue, probe, prune, or stop using cheap replay before live calls. ([arXiv][2])

Implement:

```text
src/acp/routing/topology_program.py
src/acp/routing/topology_program_executor.py
src/acp/routing/topology_safety.py
src/acp/routing/topology_policy_store.py
src/acp/evaluation/topology_live_ablation.py
```

Topology actions:

```text
cheap_single
ask_readonly_advisor
retry_with_grep
retry_with_repo_map
retry_with_memory
sample_k_candidates
branch_parallel
run_strict_verifier
route_to_human
abstain
commit_success
terminate_failure
```

Safety invariants:

```text
- high-risk task cannot skip strict verifier
- public-test-only success cannot auto-approve security tasks
- branch_parallel uses isolated workspaces
- all losing branches are archived as training examples
- controller cannot exceed budget class
```

Live acceptance:

```text
- run topology_controller on at least 100 hard-realism tasks
- compare against cheap_single, grep_router, repo_map_router
- report marginal value of each topology action
- promote only bucket-level actions with positive expected value
```

This is where ACP becomes a true metarouter rather than a static selector.

### P3 — Advisor v3: calibrated read-only critique at scale

Advisor v2 exists, but Alpha 43 says the scaled 318-cell run did not include tool-loop advisor/best-of-k at scale; those were smaller/deterministic modules.  Next sprint should scale advisor on hard tasks.

This aligns with MetaCogAgent’s core idea: agents should estimate capability alignment and delegate low-confidence tasks rather than overconfidently execute. ([arXiv][3]) Conductor is also relevant because it learns orchestration strategies over arbitrary worker pools, including topologies and targeted prompts. ([arXiv][4])

Implement:

```text
src/acp/routing/advisor_v3.py
src/acp/evaluation/advisor_calibration_report.py
src/acp/finops/advisor_value_model.py
src/acp/schemas/advisor_trace.py
```

Advisor trigger model:

```text
context_sufficiency_low
cheap_agent_low_bucket_success
first_attempt_failed
tests_not_run
hidden_verifier_uncertain
diff_too_broad
risk_high
memory_negative_prior_hit
provider_activation_risk
```

Advisor modes:

```text
file_selection_advice
test_plan_advice
patch_critique
risk_review
spec_gap_detection
```

Hard rules:

```text
- advisor is read-only
- advisor cannot override deterministic verifier failure
- advisor cannot write patches
- advisor must be traced and budgeted
- advisor advice is evidence, not authority
```

Acceptance:

```text
- >=100 advisor-eligible hard tasks
- advisor improves verified success or reduces false auto-approve in at least one bucket
- advisor global cost_per_verified_success does not regress >10%
- no-op advisor calls are flagged as waste
- policy dossier explains why advisor was or was not called
```

### P4 — Best-of-k v3 with diversity and proof selection

Alpha 43 notes best-of-k diversity/pruning live was deferred.  It should not be “same prompt twice.” It should sample different context/topology/harness strategies and select by verifier/comparator signals.

Implement:

```text
src/acp/routing/candidate_sampler_v3.py
src/acp/routing/candidate_diversity.py
src/acp/routing/candidate_pruning.py
src/acp/evaluation/proof_signal_selector_v3.py
src/acp/evaluation/candidate_comparator_report.py
```

Diversity arms:

```text
grep_context
repo_map_context
memory_context
test_first_prompt
minimal_patch_prompt
security_hardened_prompt
advisor_seeded_prompt
cheap_then_strong_repair
```

Comparator signals:

```text
public_tests
hidden_tests
semantic_patch_equivalence
diff_minimality
forbidden_file_touch
test_gaming_detector
security_detector
runtime/performance
post_merge_risk_score
```

Acceptance:

```text
- k=3 and k=5 tested separately
- early stop saves cost when first candidate is verified
- public-pass/hidden-fail loses
- broad unrelated diff loses
- best-of-k reports waste rate
- best-of-k promoted only in buckets where marginal value > 0
```

The goal is not to prove best-of-k is always good. The goal is to learn **where** it is worth spending.

### P5 — Context strategy science: grep vs repo-map vs embedding vs memory

The current `context_strategy_ope_v2` has a useful result but a big gap: no embedding samples and no broad-repo-map samples.   The previous repo-map work showed a strong mechanism and live win: Aider-style repo-map gave **21× API coverage per token** and live A/B improved **0/3 → 3/3** on a cross-file task.  But Alpha 43 says grep edged repo-map at scale. Both can be true; ACP should learn the regimes.

Implement:

```text
src/acp/context/context_experiment_matrix.py
src/acp/context/context_strategy_bandit_v3.py
src/acp/context/context_reuse_economics.py
src/acp/context/context_noise_stress.py
```

Experiment buckets:

```text
exact_symbol
cross_file_api
broad_repo_map
memory_required
large_repo_with_decoys
generated_file_noise
deprecated_api_collision
security_sensitive_context
```

Strategies:

```text
minimal
grep
repo_map
embedding
hybrid_keyword_embedding
grep_plus_repo_map
repo_map_plus_memory
negative_memory_only
```

Metrics:

```text
verified_success
hidden_test_pass
context_build_latency
context_token_cost
API coverage per token
definition recall
callsite recall
decoy false-positive rate
secret leakage
cost_per_verified_success
```

Acceptance:

```text
- at least 20 samples in each major context bucket
- embedding is tested honestly, not assumed
- grep-vs-embedding no longer reports insufficient evidence
- repo_map promoted only where it beats grep or supplies lower token cost
- memory context tested separately from repo context
```

### P6 — Memory v3: longitudinal reliability, revision, and poisoning

The memory ablation is the most promising Alpha 43 result after the arena itself: memory solved **25/30** vs **11/30** baseline and cut cost per verified success materially.  Now it needs to become long-lived and robust.

AgingBench is directly relevant: it argues long-lived agents should be evaluated for compression aging, interference aging, revision aging, and maintenance aging across the memory pipeline. ([arXiv][5]) MeMo is also relevant because it treats memory as a modular subsystem rather than just retrieval snippets. ([arXiv][6])

Implement:

```text
src/acp/memory/memory_graph.py
src/acp/memory/memory_revision_policy.py
src/acp/memory/memory_decay_policy.py
src/acp/memory/memory_poisoning_detector.py
src/acp/evaluation/memory_lifespan_benchmark.py
```

Memory records should include:

```text
repo_family
task_type
failure_signature
context_need
agent
topology
context_strategy
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
superseded_by
```

Aging scenarios:

```text
compression aging
interference aging
revision aging
maintenance aging
negative-memory staleness
repo-convention migration
post-merge revert repair
```

Acceptance:

```text
- 100-session simulated project history
- memory precision/recall tracked over time
- post-merge revert revises memory
- stale memory decays unless reconfirmed
- poisoned memory quarantined
- cross-tenant reads blocked
- memory improves repeated-pattern cost_per_verified_success vs no-memory
```

This is a key product differentiator: ACP becomes an organizational coding memory, not just a router.

### P7 — Harness evolution as guarded PRs

Alpha 43 deferred harness-evolution guarded-PR loop.  The recent Meta-Harness and Agentic Harness Engineering papers are directly on point: they argue harness code/interfaces can be optimized from source, traces, and scores, not just hand-tuned prompts. Meta-Harness reports gains from searching harness code using previous candidates’ scores and traces. ([arXiv][7]) Agentic Harness Engineering frames harness evolution around component observability, experience observability, and decision observability, and reports pass@1 improvements on Terminal-Bench 2. ([arXiv][8])

Implement:

```text
src/acp/training/harness_failure_clustering.py
src/acp/training/harness_patch_proposal.py
src/acp/training/harness_component_registry.py
src/acp/training/harness_canary_runner.py
src/acp/training/harness_guarded_pr_loop.py
```

Flow:

```text
conclusive failed traces
  -> cluster failure mode
  -> propose bounded harness patch
  -> self-declared expected effect
  -> static/security scan
  -> regression suite
  -> negative-transfer suite
  -> hard-realism canary
  -> guarded PR
  -> rollback metadata
```

Editable components:

```text
tool schema
finish discipline
test-running discipline
grep/repo-map presentation
memory snippet presentation
advisor trigger
best-of-k diversity prompts
budget policy
error/nudge handling
```

Acceptance:

```text
- 3 patch proposals generated from real failure clusters
- at least 1 rejected for negative transfer
- at least 1 rejected for no measured lift
- no direct protected branch writes
- no promotion without canary lift
- every harness patch has rollback metadata
```

### P8 — Production-ish deployment gate

Alpha 43 deferred production k8s/queue deployment.  This matters because a metarouter has more moving parts than a coding agent. It needs a production-ish proof: API, queue, workers, artifact store, database, sandbox isolation, concurrency, and observability.

Implement:

```text
deploy/local_prod/
  docker-compose.yml
  kind-or-k3d.yaml
  postgres
  minio
  redis
  api
  worker
  sandbox-runner

src/acp/deploy/worker_queue.py
src/acp/deploy/artifact_store.py
src/acp/deploy/production_health_gate.py
```

Acceptance:

```text
- API schedules; worker executes
- Postgres stores entities
- object store stores artifacts
- 100 concurrent jobs complete
- no duplicate run IDs
- no orphan workspaces/pods
- no secret leakage
- p95 latency reported
- health fails if deployment artifact stale
- NetworkPolicy enforcement live-tested when CNI supports it
```

This is the “can this run all week?” milestone.

### P9 — Operator learning loop

Alpha 43 deferred the operator loop.  The product should not just automate; it should learn from human review and make that visible.

Implement:

```text
src/acp/review/operator_inbox_v2.py
src/acp/review/label_quality.py
src/acp/review/active_learning_priority.py
src/acp/review/policy_update_from_labels.py
src/acp/review/operator_finops.py
```

Metrics:

```text
reviewer_agreement
override_rate
label_latency
false_auto_approve_near_miss
policy_changed_after_label
human_review_cost_proxy
most_informative_task_buckets
```

Acceptance:

```text
- active learner selects high-value review items
- label changes a future routing decision in replay
- disagreement blocks learning
- high-risk labels remain advisory until gates pass
- operator sees why the item matters
```

### P10 — Provider marketplace, but Anthropic-only live

Provider contracts pass, but the current environment does not have provider keys/binaries; the provider report marks all providers unavailable with reasons and passes contract tests.  That’s acceptable. The next step is to model providers as a marketplace without needing live OpenAI/Gemini.

Implement:

```text
src/acp/providers/marketplace.py
src/acp/providers/provider_scorecard.py
src/acp/providers/provider_replay_import.py
src/acp/finops/provider_mix_optimizer.py
```

Rules:

```text
- Anthropic live evidence may drive local policy here.
- OpenAI/Gemini remain hooks + mocked contracts here.
- External provider logs can be imported later as replay datasets.
- unavailable provider != bad provider.
- no provider ranking without conclusive cells.
```

Acceptance:

```text
- provider scorecard separates live, replay, mock-contract, unavailable
- provider mix optimizer only recommends feasible providers
- OpenAI/Gemini can be plugged in later without changing arena schema
- no live claim for OpenAI/Gemini in this environment
```

## The Alpha 44 command surface

Ask the coding agent to produce these commands:

```bash
uv run acp hard-arena run \
  --tasks 100 \
  --target-conclusive-cells 600 \
  --policies cheap_single,grep,repo_map,memory,advisor,best_of_k,topology_controller,abstain \
  --hidden-tests \
  --persist

uv run acp issue-replay freeze --input evals/issue_replay/sources.yaml
uv run acp issue-replay run --bundle evals/issue_replay/bundles --persist

uv run acp topology live-ablation --from latest-hard-arena
uv run acp memory lifespan --sessions 100
uv run acp harness evolve --from latest-hard-arena --dry-run-pr
uv run acp finops marginal-value --from latest-hard-arena
uv run acp provider scorecard --show-unavailable
uv run acp reports claim-check
uv run acp health --mode production
```

Required artifacts:

```text
reports/alpha44_report.md
reports/hard_realism_arena.json
reports/hard_realism_policy_compare.json
reports/hard_realism_failure_taxonomy.json
reports/issue_replay_bundles.json
reports/topology_live_ablation.json
reports/advisor_v3_calibration.json
reports/best_of_k_v3.json
reports/context_experiment_matrix.json
reports/memory_lifespan_benchmark.json
reports/harness_evolution_guarded_pr.json
reports/productionish_deploy_gate.json
reports/operator_learning_loop.json
reports/provider_marketplace_scorecard.json
reports/finops_marginal_value_hard.json
reports/claim_evidence_map_alpha44.json
```

## Definition of done

Alpha 44 is done only if:

```text
- full suite green
- ruff + mypy clean
- alembic upgrade head clean
- acp reports validate clean
- acp reports claim-check clean
- >=600 conclusive hard-realism cells
- >=100 hard tasks
- high-risk false auto-approve = 0
- cheap_single fails on enough tasks to avoid ceiling-only conclusions
- at least one bucket-level metarouting policy beats cheap_single with CI separation
- memory improves repeated-pattern tasks over time
- context strategy experiment includes grep, repo_map, embedding, hybrid, memory
- topology controller executes live, not just offline search
- advisor/best-of-k are evaluated at hard-arena scale or honestly restricted
- OpenAI/Gemini remain hooks only, no live claim
```

## Coding-agent instruction block

Give the coding agent this:

```text
Implement Alpha 44: Hard-Realism MetaRouter.

Use Alpha 43 as baseline. Do not redo the scaled arena except where needed. The Alpha 43 result showed a ceiling effect: routed policies had excellent point estimates but no CI-separated win over cheap_single. Your mission is to build the hard-realism evaluation and executable orchestration needed to find where metarouting has real value.

Priorities:
1. Hard-Realism Arena: >=100 tasks, >=600 conclusive cells, hidden tests, harder task families.
2. Real GitHub issue replay bundles, offline-first.
3. Executable topology controller live: advisor/retry/branch/best-of-k/abstain/strict-verify.
4. Advisor v3: calibrated read-only critique and marginal-value gating.
5. Best-of-k v3: diverse candidates + proof-signal comparator + early stop.
6. Context experiment matrix: grep vs repo_map vs embedding vs hybrid vs memory.
7. Memory v3: lifespan benchmark, revision, decay, poisoning defense.
8. Harness evolution as guarded PRs from real failure clusters.
9. Production-ish deployment gate: API + queue + worker + artifacts + DB + concurrency.
10. Operator learning loop and provider marketplace scorecard.

Hard rules:
- unavailable provider != capability failure
- OpenAI/Gemini are mocked hooks only here
- no contaminated sample enters capability/OPE/promotion
- no high-risk task can skip strict verifier
- no public-test-only success can auto-approve security tasks
- no policy promotion without CI separation or explicitly scoped bucket-level evidence
- every claim must map to fresh, uncontaminated evidence

Finish only when:
uv run pytest -q -n 2
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
acp reports validate
acp reports claim-check
are all green.
```

## What to skip

Do not spend Alpha 44 on:

```text
- scaling the same easy task distribution
- OpenAI/Gemini live work in this environment
- synthetic-only wins without hidden tests
- new dashboards without policy decisions
- generic vector DB work without context-strategy evidence
- ungoverned harness self-edits
- LoRA or training unless tied to a concrete trace-distillation target
- model self-ranking without verifier/comparator evidence
```

## Strategic summary

Alpha 43 made ACP honest and statistically grounded. The next round should make it **undeniably differentiated**. The path is not a bigger model. It is:

```text
harder tasks
real issue replay
executable topology
memory over time
proof-selected candidates
advisor only when valuable
context strategy by evidence
FinOps as a control objective
provider hooks without false claims
claim-checked artifacts
```

The product story after Alpha 44 should be:

> ACP sits above Claude/Codex/OpenAI/Gemini/OpenHands-style agents and learns when to use each provider, context strategy, memory, advisor, candidate sampler, topology, verifier, abstention path, and budget class. It proves decisions on hard, hidden-tested coding tasks using conclusive measurement and cost-per-verified-success — and refuses to promote or claim anything the evidence does not support.

[1]: https://arxiv.org/abs/2605.15184?utm_source=chatgpt.com "Is Grep All You Need? How Agent Harnesses Reshape Agentic Search"
[2]: https://arxiv.org/abs/2605.08083?utm_source=chatgpt.com "LLMs Improving LLMs: Agentic Discovery for Test-Time Scaling"
[3]: https://arxiv.org/abs/2605.17292?utm_source=chatgpt.com "MetaCogAgent: A Metacognitive Multi-Agent LLM Framework with Self-Aware Task Delegation"
[4]: https://arxiv.org/abs/2512.04388?utm_source=chatgpt.com "Learning to Orchestrate Agents in Natural Language with the Conductor"
[5]: https://arxiv.org/abs/2605.26302?utm_source=chatgpt.com "Your Agents Are Aging Too: Agent Lifespan Engineering for Deployed Systems"
[6]: https://arxiv.org/abs/2605.15156?utm_source=chatgpt.com "MeMo: Memory as a Model"
[7]: https://arxiv.org/abs/2603.28052?utm_source=chatgpt.com "Meta-Harness: End-to-End Optimization of Model Harnesses"
[8]: https://arxiv.org/abs/2604.25850?utm_source=chatgpt.com "Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses"


-------------------------------------------

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

