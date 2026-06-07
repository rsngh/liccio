Below is the next set of instructions to build a compelling, differentiated and groundbreaking meta-agent that is truly at the leading edge and can route/delegate to other agents based on task complexity, context, etc. Lower down you'll see some research directions; some of this is implemented, and you can also look as needed at the papers on agent harnesses and context/memory in the pdfs directory, that's fine too. We should above all make sure that we're data driven -look at the evals we just did and which are recorded in the repos. If they help, great; if not, come up with more challenging and realistic live/unseen evals. In particular we haven't done much, I think, on memory and context optimization.

------------------------------------------------------------------

Understood. I would revise the next-round instructions so **OpenAI/Gemini are pluggable hooks only**, not live acceptance dependencies. The live proof in this environment should use the reachable harnesses, especially Claude, plus local/fake/codex-style adapters when available. The latest branch evidence already shows the project is green and has useful Claude/live repo-map signal, so the next sprint should optimize ACP as an **adapter-agnostic metarouter**, not as an OpenAI-vs-Claude benchmark. According to a document from June 7, 2026, the current state includes the newer live Claude corpus, repo-map work, and 1201/18/0 suite result; the earlier P1–P5 hygiene pass fixed stale claims, no-op safety, adapter discoverability, and contamination handling.  

Here is how I would change the coding-agent directive.

## Updated principle

**Do not block this sprint on OpenAI/Gemini live access.**

Build:

```text
openai_harness hook
gemini_harness hook
provider registry entries
health/down reasons
mocked contract tests
cost model placeholders
trace normalization
```

But live acceptance should require only:

```text
claude_harness if reachable
codex_cli if installed
openhands if available
local/fake/patch baselines
mock OpenAI/Gemini contract tests
```

The product claim should be:

> ACP can route across heterogeneous coding-agent backends through a normalized harness contract, and the routing/evaluation/FinOps loop works even when some providers are unavailable.

Not:

> ACP currently proves OpenAI/Gemini parity in this environment.

## Replace OpenAI/Gemini live gates with provider-contract gates

Add a provider contract suite:

```text
tests/contracts/test_provider_harness_contract.py
```

Each provider adapter must satisfy:

```text
health() returns available=false with actionable reason when SDK/key/network missing
execute() returns unavailable/infra outcome, not capability failure, when provider unavailable
trace schema is normalized even on provider failure
cost model is present, but may be estimated/unknown
provider_policy declares timeout/retry/budget behavior
no provider absence poisons capability matrix
no provider absence blocks suite
```

For OpenAI/Gemini specifically:

```text
tests/contracts/test_openai_harness_contract.py
tests/contracts/test_gemini_harness_contract.py
```

Use fake clients or monkeypatched SDK shims. Do **not** require real network calls.

Acceptance:

```text
- openai_harness appears in `acp agents list` as down/unavailable with a reason.
- gemini_harness appears in `acp agents list` as down/unavailable with a reason.
- both pass mocked tool-loop contract tests.
- both are excluded from live capability claims unless conclusive live cells exist.
```

## Revise the MetaRouter Arena adapter matrix

Use this live/default matrix:

```text
live_required:
  claude_harness
  fake
  patch

live_optional_self_skip:
  codex_cli
  openhands
  docker/kubernetes-backed execution
  openai_harness
  gemini_harness

mock_contract_only:
  openai_harness
  gemini_harness
```

Arena reports should separate:

```text
adapter_status:
  live_conclusive
  live_inconclusive
  unavailable
  mock_contract_only
  fixture_only
```

This avoids making unavailable providers look like bad agents.

## Updated P0 — MetaRouter Arena should be provider-agnostic

Keep the arena, but change acceptance from “compare OpenAI/Claude/etc.” to:

```text
Compare:
  current_acp_router
  always_claude_harness
  cheap_single
  advisor_router
  best_of_k_router
  repo_map_router
  memory_router
  fake/patch baselines

Optionally include:
  codex_cli
  openhands
  openai_harness if live key available
  gemini_harness if live key available
```

Required metrics:

```text
cost_per_verified_success
verified_success_rate
hidden_test_pass_rate
conclusive_rate
inconclusive_rate
adapter_unavailable_rate
advisor_call_rate
best_of_k_waste_rate
context_strategy_cost
memory_hit_rate
routing_regret_vs_oracle
```

Important gate:

```text
Unavailable OpenAI/Gemini cells must count as provider availability evidence,
not capability evidence.
```

## Updated P1 — AdvisorPolicy should use Claude as the strong advisor here

In this environment:

```text
cheap_executor:
  local/weak/mock harness
  or budget-limited Claude
  or codex_cli if installed

strong_read_only_advisor:
  claude_harness
```

Later, in a provider-rich environment, swap in:

```text
openai_harness
gemini_harness
claude_harness
codex_cli
openhands
```

No code should hardcode “Claude is the advisor.” It should be policy-configured:

```yaml
advisor_policy:
  default_advisor_pool:
    - claude_harness
    - openai_harness
    - gemini_harness
  require_available: true
  unavailable_behavior: skip_and_log
```

Acceptance:

```text
- If OpenAI/Gemini unavailable, advisor policy skips them cleanly.
- Claude can serve as advisor if available.
- If no advisor is available, router falls back to strict verification/human review.
```

## Updated P2 — CandidateSampler should be model-agnostic

Do not make weak-model sampling depend on OpenAI.

Use provider pool config:

```yaml
candidate_sampler:
  cheap_candidate_pool:
    - claude_harness_budget_limited
    - local_fake_candidate
    - codex_cli
    - openai_harness
    - gemini_harness
  unavailable_behavior: skip
```

Acceptance:

```text
- k candidates can be sampled from any available cheap provider.
- OpenAI/Gemini hooks can be present but unavailable.
- comparator selects only verified candidates.
- cost_per_verified_success excludes unavailable providers from the denominator unless explicitly measuring availability.
```

## Updated P3 — TopologyControllerSearch should simulate unavailable providers

For offline controller search, include availability as a state feature:

```text
provider_available
provider_latency_bucket
provider_cost_bucket
provider_recent_infra_failure_rate
provider_recent_activation_rate
provider_recent_pwl
```

Train/evaluate controllers that can choose:

```text
skip_unavailable_provider
try_next_provider
ask_advisor
best_of_k_available_only
branch_parallel_available_only
abstain
human_review
```

Acceptance:

```text
- Controller never selects unavailable OpenAI/Gemini in this environment.
- Controller can still learn from mocked OpenAI/Gemini traces later.
- Controller report distinguishes “not tried because unavailable” from “tried and failed.”
```

## Updated P4 — Provider abstraction work to assign coding agent

Add:

```text
src/acp/providers/base.py
src/acp/providers/openai_provider.py
src/acp/providers/gemini_provider.py
src/acp/providers/anthropic_provider.py
src/acp/providers/availability.py
src/acp/providers/cost_catalog.py
```

Schemas:

```text
ProviderCapability:
  supports_tool_loop
  supports_readonly_advisor
  supports_parallel_sampling
  supports_json_tools
  supports_command_traces
  supports_token_usage
  supports_cost_estimate

ProviderAvailability:
  provider
  adapter
  available
  reason
  checked_at
  sdk_present
  key_present
  network_reachable_optional
  binary_present_optional

ProviderCostModel:
  provider
  model
  input_cost_per_million
  output_cost_per_million
  tool_call_cost
  unknown_cost_behavior
```

Acceptance:

```text
- `acp agents list --show-unavailable` shows OpenAI/Gemini hooks.
- `acp provider health` explains exactly why each unavailable provider is unavailable.
- capability matrix does not treat unavailable as failed.
- OPE excludes unavailable cells from quality estimates.
```

## Updated P5 — FinOps should optimize over available providers only

Add a hard rule:

```text
FinOps optimization is over the feasible provider set.
```

Meaning:

```text
available_provider_set = providers with:
  health.available=true
  contract_passed=true
  not_contaminated
  enough conclusive cells for the requested claim
```

FinOps report should include:

```text
potential_provider_savings_not_measured:
  openai_harness: unavailable_in_this_environment
  gemini_harness: unavailable_in_this_environment
```

Acceptance:

```text
- No recommendation says “use OpenAI/Gemini” unless they have current conclusive evidence.
- Reports may say “hook exists; live evaluation pending.”
- Claude/local/codex evidence can still drive routing in this environment.
```

## Short replacement instruction for the coding agent

Use this as the updated task block:

```text
Implement Alpha 42 as an adapter-agnostic MetaRouter + FinOps sprint.

Do not require live OpenAI or Gemini access. Build OpenAI/Gemini hooks, provider registry entries, health/down reasons, mocked contract tests, normalized trace schemas, and cost-model placeholders. Treat them as unavailable/mock-contract-only in this environment.

Use Claude as the primary live harness if reachable. Use codex_cli/OpenHands only if locally available and self-skip otherwise. Keep fake/patch baselines.

Main deliverables:
1. MetaRouter Arena with provider availability separated from capability.
2. AdvisorPolicy with configurable advisor pool and read-only consult_advisor tool.
3. CandidateSampler + ExecutionComparator + BestOfKPolicy over available providers.
4. TopologyControllerSearch that treats provider availability as a first-class state feature.
5. ContextStrategyOPE + MemoryPolicy using repo_map/grep/hybrid/memory as routable dimensions.
6. Provider abstraction layer for OpenAI/Gemini/Claude/Codex/OpenHands.
7. FinOps report optimizing cost_per_verified_success over feasible providers only.

Hard gates:
- Unavailable provider != capability failure.
- No OpenAI/Gemini live claim without conclusive live cells.
- Mocked OpenAI/Gemini hooks must pass provider-contract tests.
- Latest arena report must show conclusive rate, unavailable rate, and cost_per_verified_success.
- Any promoted routing policy must beat static baselines on verified success per dollar using only conclusive, uncontaminated cells.
```

This keeps the architecture future-proof for OpenAI/Gemini while making the next sprint realistic and still groundbreaking in the current environment.


According to a document from June 7, 2026, the branch has moved past the earlier P1–P5 hygiene round: the latest reported state is **1201 passed / 18 skipped / 0 failed**, 302 source files, 96 artifacts, a broadened live Claude corpus with **HAR=1.0, HFR=0.889, PWL=0.778, 7/9 solved, $0.048/success**, and a new `repo_map` context strategy with both deterministic and live A/B evidence: **21× API coverage per token** and **baseline 0/3 → repo_map 3/3** on a cross-file task.    The earlier June 6 report also matters because it closed the trust-baseline issues: stale test claims, deploy no-op detection, measurement contamination, adapter discoverability, no-op false success, and the xdist/nested-pytest flake.  

My recommendation: **do not make the next round “more features” in isolation. Make it an evidence-driven “MetaRouter Arena + FinOps Controller” round.** The goal should be to prove that ACP can route among Claude/Codex/OpenAI/OpenHands-style agents, context strategies, memory strategies, topologies, and advisor calls **better than any static single-agent or fixed-topology policy**, while optimizing **cost per verified success**.

## Read of the latest evals

The strongest positive signal is `repo_map`: ACP now has proof that context strategy can swing live outcomes from 0% to 100% on a cross-file task. That means context/memory should become a first-class routing dimension, not a sidecar.

The most useful negative signal is the Claude live corpus: **HAR=1.0 but HFR/PWL below 1.0**. The harness activated, but did not always follow ideal protocol or pass when loaded. That argues for **metacognitive escalation, advisor calls, proof-based candidate selection, and stricter “do not finish unless verified” topology control**, not just better prompts.

The older P1–P5 work fixed the measurement substrate, so the next layer can trust conclusive cells more than before. Specifically, `repo_replay_live` now uses canonical `build_hygiene_report`, no-op success is blocked, real adapters are discoverable, and the suite is reproducible.  

## Next round name

**Alpha 42 — Evidence-Driven MetaRouter + Agent FinOps**

Acceptance question:

> Can ACP learn when to use a cheap executor, a stronger advisor, k weak candidates, branch-parallel execution, repo-map/grep/vector context, memory, or abstention — and beat static routing on verified success per dollar?

## P0 — Build the MetaRouter Arena before adding more policy complexity

The arena should be the evaluation substrate for everything below.

**Implement:**

```text
evals/metarouter_arena/
  schema.py
  task_pack.py
  run_arena.py
  hidden_verifier.py
  policy_compare.py
  report.py
```

`ArenaTaskSpec` should include:

```text
repo_fixture | real_repo_url
base_sha
task_type
risk_level
difficulty_band
context_need: none | exact_symbol | cross_file_api | broad_repo_map | memory_required
verification: public_tests + hidden_tests + semantic_patch_judge
gold_patch_optional
forbidden_files
budget_class
```

Run each task across:

```text
always_openai_harness
always_claude_harness
always_codex_cli
cheap_static
current_acp_router
advisor_router
best_of_k_router
topology_controller_router
memory_context_router
```

Primary metrics:

```text
cost_per_verified_success
verified_success_rate
hidden_test_pass_rate
conclusive_rate
inconclusive_rate
human_review_rate
false_auto_approve_rate
adapter_activation_rate
HAR / HFR / PWL
p50/p95 latency
marginal value of extra compute
routing regret vs oracle
```

Acceptance gate:

```text
- >=50 unseen tasks in smoke, >=300 conclusive cells.
- No promotion if conclusive rate <80%.
- No promotion if false auto-approve >0 on high-risk tasks.
- No claim may cite contaminated or stale artifacts.
- Report compares against static single-agent and static topology baselines.
```

This arena is the product proof. Every other module should be judged by whether it improves this report.

## P1 — Layered advisor / metacognitive escalation

Your Tier 1 item is right, but it should be framed as **cheap executor + read-only advisor + budgeted escalation**, not “always ask a stronger model.” MetaCogAgent’s core idea is confidence/self-assessment plus delegation when capability alignment is low, and CADMAS-CTX strengthens that by making capability context-conditioned instead of static. ([arXiv][1]) ([arXiv][2])

**Implement:**

```text
src/acp/routing/advisor_policy.py
src/acp/agents/advisor_tool.py
src/acp/evaluation/advisor_ope.py
src/acp/schemas/advisor.py
```

Objects:

```text
AdvisorPolicy
AdvisorTrigger
AdvisorCall
AdvisorBudget
AdvisorTrace
AdvisorOutcome
AdvisorOPEReport
```

Advisor triggers:

```text
low verifier confidence
no changed files after attempt
tests not run
public tests pass but hidden/suspicion detector uncertain
high context entropy
low historical success for agent/task/context bucket
security_fix or migration with cheap agent selected
underspecified ticket
```

Rules:

```text
- Advisor is read-only by default.
- Advisor can recommend files/tests/strategy, not write patches.
- Advisor call must be budgeted and traced.
- Advisor result is evidence, not authority.
- Advisor cannot override deterministic verifier failure.
```

Acceptance tests:

```text
test_advisor_not_called_when_confident
test_advisor_called_on_low_confidence
test_advisor_read_only_enforced
test_advisor_budget_cap_blocks_extra_calls
test_advisor_trace_persisted
test_advisor_ope_reports_lift_and_cost
```

Live acceptance:

```text
On MetaRouter Arena:
  advisor_router improves verified success or reduces false auto-approve
  cost_per_verified_success does not regress by >10%
  advisor_call_rate is reported by task_type/risk
```

## P2 — Weak-model candidate generation + execution comparator

This is the most direct FinOps lever. The recent “agentic boosting weak reasoning models” work frames the key mechanism well: repeated weak proposals can expose correct solutions, but selection needs local soundness signals such as tests, type checks, proof checks, or constraints. ([arXiv][3])

**Implement:**

```text
src/acp/routing/candidate_sampler.py
src/acp/evaluation/execution_comparator.py
src/acp/evaluation/proof_signal_selector.py
src/acp/routing/best_of_k_policy.py
src/acp/evaluation/cost_per_verified_success.py
```

Core flow:

```text
task
  -> sample k cheap candidates in isolated workspaces
  -> run deterministic verifier on each
  -> run hidden tests / semantic judge where configured
  -> reject no-op / suspicious / broad-diff candidates
  -> select minimal verified patch
  -> archive all candidates as training examples
```

Policy knobs:

```text
k
cheap_model
diversity_prompt
max_total_cost
max_parallelism
early_stop_after_verified
allow_strong_fallback
```

Acceptance tests:

```text
test_best_of_k_selects_only_verified_candidate
test_public_pass_hidden_fail_loses
test_noop_candidate_loses
test_broad_unrelated_diff_loses
test_early_stop_saves_cost
test_all_candidates_persisted
```

Arena success criterion:

```text
best_of_k_router must beat cheap_single on verified success
and beat strong_single on cost_per_verified_success
for at least one task bucket.
```

## P3 — AutoTTS-style topology controller search

ACP already has topology actions. The next step is to stop hand-tuning them. AutoTTS is directly relevant because it searches controllers over pre-collected trajectories and probe signals, deciding when to branch, continue, probe, prune, or stop without repeatedly paying for live model calls during search. ([arXiv][4])

**Implement:**

```text
src/acp/routing/topology_controller_search.py
src/acp/routing/topology_program.py
src/acp/evaluation/offline_trace_controller_eval.py
```

Topology action space:

```text
cheap_single
strong_single
ask_advisor
best_of_k
branch_parallel
retry_with_repo_map
retry_with_grep
retry_with_memory
strict_verify
human_review
abstain
stop_success
stop_failure
```

Controller input features:

```text
task_type
risk_level
repo_size
context_strategy
context_sufficiency_score
retrieval_entropy
prior cell success
adapter HAR/HFR/PWL
first_attempt verifier result
diff size
tests_run
failure_signature
budget_remaining
```

Offline search objective:

```text
maximize:
  verified_success_reward
  - cost_penalty
  - latency_penalty
  - false_auto_approve_penalty
  - human_review_penalty
```

Acceptance tests:

```text
test_controller_never_skips_strict_verifier_for_high_risk
test_controller_branches_when_uncertainty_high
test_controller_stops_when_verified_and_budget_low
test_offline_eval_replays_trace_without_live_model_calls
test_promote_only_with_conclusive_noncontaminated_gain
```

Deliverable artifact:

```text
reports/topology_controller_search.json
reports/topology_controller_search.md
```

## P4 — Context and memory manager: repo_map is only the first proof

The latest repo-map win proves context strategy is outcome-critical. The next step is a **ContextStrategyOPE** layer that learns when to use grep, repo map, embeddings, hybrid, or memory. “Is Grep All You Need?” is directly relevant because it reports that grep can outperform vector retrieval depending on harness/tool style; that means ACP should not default to vector DB or embeddings as “the advanced option.” ([arXiv][5])

**Implement:**

```text
src/acp/context/context_strategy_ope.py
src/acp/context/context_cost_model.py
src/acp/memory/experience_bank.py
src/acp/memory/memory_policy.py
src/acp/evaluation/memory_aging_benchmark.py
```

Strategies:

```text
none
grep
repo_map
embedding
hybrid_keyword_embedding
repo_map_plus_grep
repo_map_plus_memory
memory_only_negative_prior
```

Memory record:

```text
ExperienceEpisode:
  repo_family
  task_type
  failure_signature
  context_strategy
  agent
  topology
  changed_symbols
  tests_run
  verifier_outcome
  post_merge_outcome
  reward
  cost
  skill_version
  privacy_scope
  created_at
  decay_score
```

Memory policies:

```text
write_only_conclusive
write_negative_failures
read_same_repo
read_repo_family
read_failure_signature
decay_old_memory
quarantine_poisoned_memory
```

AgingBench-style memory work should matter once ACP becomes a persistent meta-agent, because long-lived agents degrade through compression, interference, revision, and maintenance aging. ([arXiv][6])

Acceptance tests:

```text
test_context_strategy_ope_routes_cross_file_to_repo_map
test_context_strategy_ope_routes_exact_symbol_to_grep
test_memory_write_requires_conclusive_attempt
test_negative_memory_blocks_repeated_bad_strategy
test_cross_tenant_memory_blocked
test_memory_decay_changes_retrieval_ranking
test_memory_poisoning_detector_quarantines_bad_episode
```

Live acceptance:

```text
- Reproduce repo_map 0/3 -> 3/3 class of win in at least 3 task families.
- Show grep beats embeddings on at least one exact-symbol bucket, or report null honestly.
- Show memory improves first-attempt success or cost on repeated failure-signature tasks.
```

## P5 — Context sufficiency and abstention gate

This is the missing complement to context routing. Repo-map can add breadth, but ACP also needs to know when the task is underspecified or the retrieved evidence is insufficient. SURE-RAG’s useful principle is that retrieval is not verification; the system needs an auditable support/refute/insufficient decision and should abstain when evidence is insufficient. ([arXiv][7])

**Implement:**

```text
src/acp/evaluation/context_sufficiency.py
src/acp/routing/answer_or_abstain_gate.py
src/acp/routing/spec_needed_gate.py
```

Signals:

```text
required files missing
acceptance criteria absent
tests absent
ambiguous target symbol
conflicting docs/code
context pack lacks definition of referenced API
retrieval score low
model proposes broad rewrite
```

Outcomes:

```text
sufficient
insufficient_need_more_context
insufficient_need_user_spec
insufficient_need_human_review
```

Acceptance tests:

```text
test_missing_acceptance_routes_to_spec_needed
test_missing_api_definition_routes_to_repo_map_retry
test_conflicting_docs_code_routes_to_advisor_or_human
test_high_risk_insufficient_context_abstains
```

This is especially important because the latest Claude corpus included an underspecified `stats` failure mode; that should become a first-class eval bucket rather than an anecdote. 

## P6 — Meta-agent FinOps: marginal value of compute

ACP already tracks cost, but the next round should make **AI meta-agent FinOps** a product surface.

**Implement:**

```text
src/acp/finops/marginal_value.py
src/acp/finops/budget_enforcer.py
src/acp/finops/policy_cost_report.py
src/acp/finops/cost_forecaster.py
```

Metrics:

```text
cost_per_attempt
cost_per_conclusive_attempt
cost_per_verified_success
cost_per_hidden_test_success
advisor_cost_share
best_of_k_wasted_candidate_rate
parallel_branch_waste
token_cost_by_context_strategy
latency_cost_tradeoff
marginal_value_of_next_agent_call
```

Budget classes:

```text
cheap_docs
normal_bugfix
high_risk_security
migration
incident
research_engineering
```

Acceptance tests:

```text
test_budget_blocks_best_of_k_when_marginal_value_negative
test_security_fix_allows_more_spend_than_docs
test_finops_report_attributes_cost_to_context_agent_advisor_verifier
test_policy_dossier_explains_cost_tradeoff
```

Promotion gate:

```text
A new router is promotable only if:
  verified_success_rate improves at same cost, or
  cost_per_verified_success improves at same success, or
  high-risk false-auto-approve decreases with acceptable cost.
```

## P7 — Harness evolution as governed code PRs

SkillOpt handles skill documents. The next frontier is harness/interface evolution. Meta-Harness is relevant because it optimizes harness code using source code, prior scores, and execution traces rather than only text prompts. ([arXiv][8])

**Implement:**

```text
src/acp/training/harness_evolver.py
src/acp/training/harness_patch_proposal.py
src/acp/training/harness_regression_suite.py
src/acp/training/harness_canary.py
src/acp/training/harness_archive.py
```

Flow:

```text
failed conclusive traces
  -> cluster by failure mode
  -> propose bounded harness patch
  -> static/security scan
  -> regression suite
  -> negative-transfer suite
  -> live canary
  -> guarded PR only
  -> rollback plan
```

Candidate harness changes:

```text
tool schema changes
nudge wording
finish condition
test-running discipline
advisor availability
context presentation
repo_map injection format
grep result format
```

Hard rules:

```text
- No direct protected-branch write.
- No promotion without conclusive canary lift.
- No promotion if high-risk bucket regresses.
- Every harness version has rollback metadata.
```

Acceptance tests:

```text
test_harness_patch_proposal_has_diff_and_rationale
test_security_scan_blocks_secret_exfiltration_prompt
test_negative_transfer_blocks_general_regression
test_canary_promotes_only_significant_lift
test_rollback_restores_prior_harness
```

## P8 — Synthetic active benchmark builder, but only behind an acceptance gate

Synthetic generation is useful for sparse cells, but it must not become fake evidence. It should generate **candidate training/eval tasks**, then gate them by hidden tests, patch leakage checks, difficulty calibration, and baseline separability.

**Implement:**

```text
src/acp/evaluation/task_synthesizer.py
src/acp/evaluation/difficulty_band_filter.py
src/acp/evaluation/capability_gap_generator.py
src/acp/evaluation/synthetic_task_acceptance_gate.py
```

Generate tasks from observed gaps:

```text
underspecified tickets
cross-file API discovery
test-discipline failures
security remediation
migration/CI fixes
memory-required repeated bug families
```

Acceptance gate:

```text
- no direct patch leakage
- public tests fail before fix
- reference fix passes hidden tests
- at least one baseline fails
- at least one stronger policy can solve
- difficulty band calibrated from observed solve rates
```

Do not mix synthetic tasks into production claims unless reports clearly separate:

```text
source = synthetic_calibrated
source = real_unseen
source = live_vendor
source = fixture
```

## P9 — Vendor-native live gate and routing above Claude/Codex/OpenHands

You explicitly want ACP to be the layer above Claude, Codex, etc. The adapter-discoverability fix was necessary; now ACP needs a **vendor-native live gate** that is activation-aware and comparable.

**Implement:**

```text
evals/vendor_native_live/
  run_vendor_gate.py
  adapter_contract.py
  activation_matrix.py
  vendor_failure_taxonomy.py
```

Required adapters:

```text
claude_harness
openai_harness
codex_cli
openhands
fake
patch
```

Contract:

```text
- healthcheck explains unavailable vs degraded
- tool activation captured
- file writes captured
- commands captured
- diff captured
- verifier external to agent
- no secret leakage
- conclusive vs infra separated
```

Acceptance:

```text
- Each live-capable adapter has >=30 conclusive cells before ranking claims.
- Degraded adapters are discoverable but not routed by default.
- Capability matrix shows HAR/HFR/PWL by adapter and task type.
- Router can choose “unavailable -> fallback” without poisoning learning.
```

## P10 — Long-lived memory and policy aging benchmark

This is Tier 2, but I would start the scaffolding now because ACP’s moat is the loop over time. It needs to know whether memory and learned policies get better or stale.

**Implement:**

```text
evals/aging/
  run_memory_aging.py
  run_policy_aging.py
  aging_report.py
```

Aging failure modes:

```text
compression aging
interference aging
revision aging
maintenance aging
policy drift
context-strategy drift
skill negative transfer
```

Acceptance:

```text
- 30-session simulated project history.
- Memory retrieval precision/recall tracked over time.
- Negative memory decays unless reconfirmed.
- Old repo conventions are revised after migration.
- Drift demotion fires on stale policy under changed task distribution.
```

## One-sprint implementation order

Give the coding agent this sequence:

```text
1. MetaRouter Arena schema + runner + policy comparison report.
2. AdvisorPolicy / consult_advisor with read-only enforcement and budget.
3. CandidateSampler + ExecutionComparator + ProofSignalSelector.
4. FinOps report: cost_per_verified_success and marginal value of compute.
5. ContextStrategyOPE: repo_map vs grep vs hybrid vs embeddings.
6. ContextSufficiencyJudge + AnswerOrAbstainGate.
7. TopologyControllerSearch over stored traces.
8. Vendor-native live gate with activation-aware adapter matrix.
9. HarnessEvolver proposal pipeline behind guarded PRs.
10. MemoryPolicy + ExperienceBank + first aging smoke benchmark.
```

## Concrete “definition of done” for the round

The round is done only when this command set exists and produces committed artifacts:

```bash
uv run acp eval metarouter-arena \
  --tasks 50 \
  --adapters openai_harness,claude_harness,codex_cli,openhands \
  --policies current,advisor,best_of_k,topology_controller \
  --context-strategies grep,repo_map,hybrid_keyword_embedding \
  --hidden-tests \
  --persist

uv run acp policy compare --from latest-arena
uv run acp finops report --from latest-arena
uv run acp context strategy-ope --from latest-arena
uv run acp health --mode production
```

Required artifacts:

```text
reports/metarouter_arena.json
reports/metarouter_policy_compare.json
reports/finops_cost_per_verified_success.json
reports/context_strategy_ope.json
reports/advisor_ope.json
reports/best_of_k_comparator.json
reports/topology_controller_search.json
reports/vendor_native_live_gate.json
reports/memory_aging_smoke.json
```

Pass criteria:

```text
- >=300 conclusive cells total.
- advisor or best_of_k or topology_controller beats current router on cost-normalized reward.
- repo_map win is reproduced in more than one task family, not just one hand-built task.
- grep beats vector/hybrid in at least one exact-symbol bucket, or the null result is reported.
- no contaminated sample updates capability/OPE/promotion.
- high-risk false auto-approve remains 0.
- docs claim checker maps every headline claim to fresh artifacts.
```

## What to skip this round

Skip:

```text
pretraining
large-scale RL
LoRA unless a GPU and clear target exist
more static dashboards without policy decisions
more synthetic-only scorecards
new adapters that do not emit normalized traces
model self-ranking without deterministic verifier signals
```

The near-term moat is not “more agents.” It is **measured orchestration**: confidence-aware delegation, proof-selected weak candidates, context/memory routing, topology search, and FinOps-aware promotion. The latest evals show ACP is finally ready to test that thesis directly.

[1]: https://arxiv.org/abs/2605.17292?utm_source=chatgpt.com "MetaCogAgent: A Metacognitive Multi-Agent LLM Framework with Self-Aware Task Delegation"
[2]: https://arxiv.org/abs/2604.17950?utm_source=chatgpt.com "CADMAS-CTX: Contextual Capability Calibration for Multi-Agent Delegation"
[3]: https://arxiv.org/abs/2605.14163?utm_source=chatgpt.com "Agentic Systems as Boosting Weak Reasoning Models"
[4]: https://arxiv.org/abs/2605.08083?utm_source=chatgpt.com "LLMs Improving LLMs: Agentic Discovery for Test-Time Scaling"
[5]: https://arxiv.org/abs/2605.15184?utm_source=chatgpt.com "Is Grep All You Need? How Agent Harnesses Reshape Agentic Search"
[6]: https://arxiv.org/abs/2605.26302?utm_source=chatgpt.com "Your Agents Are Aging Too: Agent Lifespan Engineering for Deployed Systems"
[7]: https://arxiv.org/abs/2605.03534?utm_source=chatgpt.com "SURE-RAG: Sufficiency and Uncertainty-Aware Evidence Verification for Selective Retrieval-Augmented Generation"
[8]: https://arxiv.org/abs/2603.28052?utm_source=chatgpt.com "Meta-Harness: End-to-End Optimization of Model Harnesses"


------------------------------------------------------------------

# RESEARCH DIRECTIONS (ORIGINAL PAPERS IN PDFS DIRECTORY)

## Tier 1 — implement next ### 1. **Layered advisor / metacognitive escalation** Implement a cheap executor that can consult a stronger read-only advisor only when confidence drops. This combines the Harvey-style advisor pattern with MetaCogAgent’s confidence-driven delegation and Conductor’s learned orchestration idea. MetaCogAgent explicitly routes low-confidence tasks to delegation; Conductor trains a small orchestrator to design topology and targeted prompts for worker agents. ([GitHub][1]) ([GitHub][1]) **ACP module:**
text
AdvisorPolicy
AdvisorCall
consult_advisor tool
advisor_budget
advisor_trace
advisor OPE/cost report
--- ### 2. **Weak-model candidate generation + verifier/comparator** Shortlist this immediately. Weak-Model Critic-Comparator shows cheap models can match frontier SWE-bench performance by sampling k candidates and selecting via execution/proof signals instead of self-ranking. ([GitHub][1]) **ACP module:**
text
CandidateSampler
ExecutionComparator
ProofSignalSelector
BestOfKPolicy
cost_per_verified_success
This is directly useful for coding agents. --- ### 3. **AutoTTS-style controller search for topology** ACP already has topology actions. AutoTTS reframes test-time scaling as controller synthesis over pre-collected traces, so strategies can be searched offline instead of hand-tuned. ([GitHub][1]) **ACP module:**
text
TopologyControllerSearch
offline_trace_controller_eval
skip/retry/branch/verify policy search
This should optimize when to branch, verify, ask advisor, or stop. --- ### 4. **Meta-Harness / Life-Harness style harness optimization** SkillOpt optimizes skills. Next, optimize **harness code and interfaces**. Meta-Harness automatically searches over harness code using prior scores and execution traces, while Code as Agent Harness argues harnesses should be executable, inspectable, stateful, and governed. ([GitHub][1]) ([GitHub][1]) **ACP module:**
text
HarnessPatchProposal
HarnessCandidate
HarnessRegressionSuite
HarnessCanary
HarnessRollback
This is the natural extension beyond skill docs. --- ### 5. **Synthetic task-corpus generator / active benchmark builder** General-Agent builds a self-evolving synthetic task corpus with difficulty calibration. ACP needs this to grow capability-matrix cells cheaply. ([GitHub][1]) **ACP module:**
text
TaskSynthesizer
DifficultyBandFilter
CapabilityGapGenerator
SyntheticTaskAcceptanceGate
Use it to populate sparse routing/skill cells. --- ## Tier 2 — important, after the next sprint ### 6. **Context-strategy optimizer: grep vs embeddings + deployment-aware context** “Is Grep All You Need?” argues grep can match or beat embeddings in coding-agent tasks when the harness is right. The Efficiency Frontier argues context strategy should be chosen by cost/performance/reuse regime. ([GitHub][1]) ([GitHub][2]) **ACP module:**
text
ContextStrategyOPE
grep_vs_embedding_bakeoff
reuse_aware_context_cost_model
Do not default to vector DB. --- ### 7. **Memory lifecycle / aging benchmark** MeMo treats memory as a learned subsystem with read/write/integrate interfaces, while AgingBench frames long-lived agent degradation as compression/interference/revision/maintenance aging. ([GitHub][1]) ([GitHub][2]) **ACP module:**
text
MemoryPolicy
MemoryAgingBenchmark
MemoryRevisionAudit
MemoryPoisoningDetector
This matters once ACP runs over weeks/months. --- ### 8. **Stochastic–deterministic boundary formalization** Production Agent Architecture Methodology introduces the stochastic-deterministic boundary: proposer, verifier, commit, reject. ACP already has this implicitly; make it explicit. ([GitHub][1]) **ACP module:**
text
SDBContract
ProposeVerifyCommitReject
DeterministicCommitGate
This improves auditability and safety. --- ### 9. **Selective abstention / “sufficient context” gates** Selective RAG work shows models often hallucinate even with sufficient context and need answer/abstain gates; this maps to ACP viability and measurement quality. ([GitHub][3]) **ACP module:**
text
ContextSufficiencyJudge
AnswerOrAbstainGate
SpecNeededGate
Especially useful for vague tickets. --- ### 10. **Workflow distillation / agentless training** Kimi-Dev and workflow-distillation-style work suggest coding workflow priors can be trained into smaller models after enough traces. Kimi-Dev reports agentless training as a software-engineering prior and trajectory fine-tuning improving SWE-Agent-like performance. ([GitHub][3]) **ACP module:**
text
TraceDistillationDataset
WorkflowPriorTrainer
small_model_router_or_repair_model
This is later than SkillOpt, but important. --- ## Tier 3 — researchy, but worth tracking ### 11. **HeavySkill / internalized parallel-deliberation skill** HeavySkill says the useful harness may boil down to an inner skill: parallel reasoning followed by deliberation, portable across harnesses and trainable. ([GitHub][1]) Use it as a SkillOpt target:
text
parallel_attempt_skill
deliberate_then_commit_skill
--- ### 12. **Tool-use RL / format-adherence training** Tool-N1 trains tool use with binary functional/format rewards rather than SFT trajectories. This maps to ACP’s HAR/HFR/PWL and vendor harness tool-call format failures. ([GitHub][3]) Use for:
text
tool_call_format_model
harness_activation_finetune
--- ### 13. **DGM / open-ended self-improving agents** Darwin Gödel Machine modifies its own codebase and keeps successful variants in an archive. Useful, but dangerous. ACP should only adopt it behind harness-update PRs, sandboxing, and canaries. ([GitHub][3]) Use for:
text
HarnessCodeEvolutionArchive
--- ### 14. **DeepConf / confidence-based trace pruning** Deep Think with Confidence uses intrinsic confidence to prune reasoning paths and save tokens. ([GitHub][3]) Use for:
text
candidate_pruning
advisor_trigger
early_stop_policy
--- ### 15. **Agent benchmark hardening: NanoGPT-Bench / rebuild-a-breakthrough** NanoGPT-Bench and Connect Four AlphaZero-style tasks test real research-engineering loops instead of patch-only fixes. ([GitHub][2]) ([GitHub][1]) Use for ACP’s hard eval suite. --- ## My recommended implementation order
text
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
## What to skip for now Do not prioritize:
text
pretraining methods
mechanistic neuron/circuit interventions
scientific forecasting benchmarks
general math discovery systems
large-scale RL training
They are interesting, but ACP’s near-term moat is **routing, measurement trust, harness/skill optimization, live vendor proof, and cheap-frontier hybrid execution**. [1]: https://raw.githubusercontent.com/dair-ai/AI-Papers-of-the-Week/main/years/2026.md "raw.githubusercontent.com" [2]: https://github.com/dair-ai/AI-Papers-of-the-Week/blob/main/years/2026.md "AI-Papers-of-the-Week/years/2026.md at main · dair-ai/AI-Papers-of-the-Week · GitHub" [3]: https://raw.githubusercontent.com/dair-ai/AI-Papers-of-the-Week/main/years/2025.md "raw.githubusercontent.com"
