Below is the next set of instructions to build a compelling, differentiated and groundbreaking meta-agent that is truly at the leading edge and can route/delegate to other agents based on task complexity, context, etc. Lower down you'll see some research directions; some of this is implemented, and you can also look as needed at the papers on agent harnesses and context/memory in the pdfs directory, that's fine too. We should above all make sure that we're data driven -look at the evals we just did and which are recorded in the repos. If they help, great; if not, come up with more challenging and realistic live/unseen evals. In particular we haven't done much, I think, on memory and context optimization.

------------------

# FEEDBACK

Straight answer: **the engineering and measurement discipline are genuinely strong; the "AI performance" win is real but smaller and more engineered than the headline numbers suggest.**

Here's the honest breakdown:

**What's genuinely good**
- The *measurement* is trustworthy. Hidden-test verification, Wilson confidence intervals, "conclusive vs infra" separation, and a claim-checker that blocks overclaiming — that's the part most agent demos skip, and it's done well. When I say "654 cells, 100% conclusive, CIs don't overlap," that's a real, reproducible, statistically-honest result.
- On the hard tasks, routing to the right context genuinely beats the cheap baseline (≈0.88 vs 0.39) with non-overlapping confidence intervals. That's a real effect, not noise.

**The big caveat you should weigh heavily**
- I *engineered* the hardness. The ceiling-breaker tasks put the answer (a random constant) in a file the cheap policy literally never sees. So "metarouting wins" mostly means **"showing the model the right file wins"** — which is almost tautological. It proves *that context matters and ACP can route it*, but it's not the model being cleverer; it's plumbing.
- On *naturally* hard tasks (Alpha 43), the same routing **could not** beat a strong cheap baseline with confidence, because Claude Sonnet already solves easy/medium bugs from almost nothing. That negative result is the more honest signal about real-world value.

**Scale and realism are modest**
- Tasks are small synthetic fixtures (one buggy function + a helper file), not real repositories. "Issue replay" is frozen-synthetic, not actual GitHub history (no network). Costs are tiny ($0.001–0.05/task), which is great, but it's smoke-to-medium scale, not production volume.
- The deploy gate, harness-evolution canary, and operator loop are *simulations* of the real thing — the logic is tested, but nothing ran on real infra under real load.

**Plain-language verdict**
Think of it as: *a very well-instrumented, honest lab that has proven the control-plane mechanics work and that context routing helps when it should — but has not yet shown it makes a frontier coding agent meaningfully better on real-world work.* The moat candidate is **measurement trust + memory-over-time**, not raw task-solving. The most valuable thing here isn't a benchmark score — it's that the system refuses to lie to you about its own results.

Mostly **something else** — harder benchmarks are the smaller lever, and "harder" in the wrong way actively misleads.

Here's how I'd rank what actually advances it:

**1. Real model/provider heterogeneity (the #1 gap).**
The whole premise — "a meta-router *above* agents that picks the cheapest capable one" — is only half-testable right now because there's effectively **one model** (Claude Sonnet). With a single strong model, "routing" collapses into "context routing." The product's main economic claim (use a cheap model, escalate to a strong one only when needed) can't be demonstrated without at least two genuinely different tiers — e.g., a weak local model + Claude. Get that, and best-of-k, advisor escalation, and FinOps suddenly have something real to optimize. This matters far more than task difficulty.

**2. Real, naturally-hard workloads — not engineered-hard ones.**
My hard arena "win" is partly a trick: I put the answer in a file the cheap policy can't see, so routing wins almost tautologically. More synthetic hardness just repeats that. What advances the thesis is **real repositories and real GitHub issues** (SWE-bench-style) where difficulty and context-needs occur naturally and even a strong agent fails a meaningful slice. That needs network/data this environment doesn't have — it's a data-access problem, not a cleverness problem.

**3. Longitudinal value, on evolving repos.**
The single most *differentiated* result was memory (better over time; recovers after a convention migration). A stateless frontier agent can't do that. Proving it over weeks/many sessions on real repos is where a control plane genuinely beats a bare agent — and it's underexplored.

**4. Verification for tasks hidden tests can't score.**
The genuinely model-hard work — large-repo orientation, multi-step features, performance, ambiguous specs needing abstention — mostly *can't* be graded by a pytest hidden test. Advancing there needs semantic judges / human-in-the-loop eval, which is a measurement problem, not a benchmark-size one.

**What I'd explicitly stop doing:** building more router/eval machinery and more synthetic scorecards. There are diminishing returns; the system is already over-instrumented relative to what it's actually been shown to do.

**Blunt version:** the project has proven the *mechanics* and the *honesty*. To prove *value*, it needs heterogeneous models to route between, real workloads to route on, and time to let memory compound — roughly in that order. Without #1 and #2, harder benchmarks will keep producing impressive-looking numbers that don't tell you whether anyone should use this.


------------------

# INSTRUCTIONS FOR NEXT ROUND

The prior Darwin-integrated work is committed. But the user pulled a "corrected" GOALS.md. Let me understand exactly what changed and verify the implementation actually matches the current GOALS.md — not trust prior summaries.

Now it's clear: the "correction" restored the **Darwin-integrated v1** GOALS (this repo's real roadmap) over the misrouted Alpha 44 content. Tasks 1–15 were committed in the prior session. My job now is to **verify completion against this exact GOALS.md, run the evals, and produce the report**. Let me verify rather than trust.

The prior commits exist but `docs/` and `sxcore/evals/` don't. Let me see what those commits actually changed and the real structure of `sxcore/`.

Everything lives under `sxcore/` (nested package). Let me verify against the correct paths.

The real paths are `sxcore/sxcore/evals/...` and `sxcore/docs/...`. Let me verify the full implementation state and run the actual gates.

120 tasks confirmed. Now let me run the actual gates and tests to verify the implementation works end-to-end. Let me find the relevant Make targets and CLI.

All 15 tasks' gates are present, including `darwin-capabilities-ready` (Tasks 7/8/9). Now let me actually **run** the test suites to verify they pass — not trust. Let me run the full integrated test set.

Dependencies aren't installed. Let me set up the environment.

Environment ready. Now let me run the full Darwin-integrated test suite and capture results.

All 42 integrated tests pass. Now let me run the actual CLI evaluator to capture real eval numbers and confirm the baseline doc's claims are reproducible.

Numbers reproduce exactly. Let me capture the detailed report and run ablation-v3 to gather full eval data.

Now ablation-v3 and the other key evaluators:

Ablation-v3: **7 distinct accept rates** (req ≥4), all arms unsafe=0.0, causal_claim=False. Let me verify the capability synthesizers (Tasks 7/8/9) and mutation closure, then check the existing baseline doc.

Tests live in `/home/user/canovaccio/sxcore/tests/`. Let me run from the correct rootdir.

Let me run the complete live-loop test set from the correct rootdir to confirm the full green state, plus run capability before/after data and check ruff.

Let me read the existing baseline doc while the test run completes.

The data fully reproduces and the baseline doc matches. Let me wait for the full test run and check ruff.

Let me gather capability and mutation-closure data while the full suite runs.

Let me capture capability synthesizer outputs and the optimizer (skill-train-v3, evolve-policy-v3) numbers.

Capability synthesizers work (domain pattern recognition, temporal compilation to 86400s). Let me check the full test run status and gather optimizer data.

The full live-loop suite finished (exit 0). Let me read its result and get the exact optimizer CLI args.

One failure: `test_multi_file_patch_records_all_hashes`. Let me investigate — run it in isolation to see if it's real or ordering-dependent.

`tests_ok=False` because the test spawns a subprocess `python -m pytest` — and the ambient `python` isn't the venv with pytest. This is an environment artifact, not a code defect. Let me confirm by putting the venv on PATH.

Confirmed — pure environment artifact (ambient `python` lacks pytest; passes with venv on PATH). Let me re-run the full live-loop suite with the venv on PATH for a clean green.

While that runs, let me get the optimizer CLI args and capture their data.

Let me verify the dossier verifies offline and detects tampering (Task 14 acceptance).

Dossier verifies offline. Let me check the full re-run.

Let me read the rest of the baseline doc while the suite runs.

The baseline doc is comprehensive and every number reproduces. Let me confirm the full re-run count.

Clean: **161 passed, 1 skipped, 0 failed** with the venv on PATH — confirming the lone earlier failure was the subprocess-`python` artifact. Let me reconcile the doc's "186" claim against the actual collectable count.

The broader `test_live_loop*.py` glob (35 files) collects 180. Let me run the complete set with venv on PATH for the true regression number.

While the full suite runs, let me verify the Task 15 demo runs end-to-end.

Demo runs exactly as documented. All 15 tasks verified. Let me check the full suite result.

The background run will notify me. Let me draft the verification report now and fill in the final count when it lands.

Let me wait for the run to finish with a monitor that emits the summary line.

While the suite finishes, let me write the verification report with the reproduced data.

Full suite: **180 passed, 1 skipped, 0 failed** with the venv on PATH. Let me fill that into the report.

Now commit and push the verification report.

Pushed to `claude/epic-darwin-9jIO8`. Here is the completion report.

## Darwin-integrated v1 — completion & verification

I pulled the corrected GOALS.md (the Darwin-integrated v1 roadmap, restored over the misrouted Alpha 44 content), then **verified Tasks 1–15 plus the 5 truth-in-claims refactor must-fixes against the current branch from a clean Python 3.12 env** — reproducing every number from the committed suite and `sxcore live-loop` CLI rather than trusting prior summaries. Report stored at `sxcore/docs/darwin_integrated_v1_verification.md` (alongside the existing `…_baseline.md`).

### Headline (`darwin-integrated`, 120 tasks) — reproduced
```
integrated_safe_accept_rate      0.6667
unsafe_acceptance_rate           0.0
accepted_without_evidence_count  0
accepted_without_shadow_count    0      (shadow-required)
accepted_without_mutation_count  0      (mutation-required)
typed_residual_count             50     residual_plan_coverage 1.0
dossier_count / coverage         70 / 1.0
shadow / mutation / workspace observed   1.0 / 1.0 / 1.0
```
**By category:** nl_simple 1.0, workspace 1.0, provider_needed 1.0, mutation_survivor 1.0 · nl_api 0.27, temporal 0.27, nl_domain 0.13 · adversarial_unsafe 0.0 (blocked), clarify 0.0 (clarified).

### Ablation v3 (Task 12) — the central fix, reproduced
**7 distinct accept rates** (req ≥4), every arm unsafe=0.0, causal_claim=False:
```
baseline 0.667  no_provider 0.524  no_workspace 0.476  no_shadow 0.438
no_mutation 0.571  no_skill 0.667  no_domain 0.648  no_api 0.629  no_temporal 0.629  evolved 0.667
```
Contributions: shadow −0.229, workspace −0.190, provider −0.143, mutation −0.095; no_skill honestly moves nothing.

### Per-task spot-checks (all run live)
- **7/8/9 capabilities:** domain→`customer-order-line_item` (Customer/Order/LineItem, conf 0.4); temporal "within 24h"→`bound_seconds=86400`; API contract+hash.
- **10 skill-train-v3:** accepted=3, rejected=20, cite_residuals=True, release_authority=False.
- **11 evolve-policy-v3:** heldout_lift=0.236, valid_rate=1.0, lint_ok=True, promotion_allowed=True.
- **13 split-check:** split_leak_count=0, operator_private_supported=True.
- **14 dossier:** decision=release, verifies_offline=True.
- **15 demo:** accepted=True, shadow_runtime_ok=True, mutation_kill 0.5→1.0, cegis=2, dossier verifies.

### Regression
- Gate tests (42) pass; **full `test_live_loop*.py`: 180 passed, 1 skipped, 0 failed**; `ruff check sxcore`: clean.
- **One environment caveat, not a code defect:** `test_multi_file_patch_records_all_hashes` fails only when the ambient `python` lacks `pytest` (the workspace test spawns `python -m pytest` as a subprocess). With the venv on `PATH` it passes — documented in the report.

**Bottom line:** all 15 tasks + 5 refactor fixes are implemented, committed, and reproduce from scratch. Hard safety invariants hold, ablation is diagnostic, every accepted row has an offline-verifiable dossier. The honest, visible frontier remains deep NL synthesis (domain 0.13 / API 0.27 / temporal 0.27) — the target for the next round.

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
