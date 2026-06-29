# External LLM/agent routers vs liccio — comparison & lessons

What we learned from three external routing efforts and what liccio adopted. The short version: liccio
independently converged on the same online, execution-grounded, cost-aware routing architecture these
works describe; the one genuinely additive idea — **per-task embedding-kNN memory** — is now implemented
(`acp.routing.memory_context`); and the hardest part (a *fair* correctness signal) is something liccio
targets and these works largely assume away.

## The three references

| | What it is | Routing mechanism | Verifier / correctness signal |
|---|---|---|---|
| **Weave Router** (workweave/router, ELv2) | Go HTTP proxy, drop-in per-request | "cluster scorer derived from Avengers-Pro": on-box embedder → cluster → per-cluster cost/quality score | none (forwards & trusts the model) |
| **Avengers-Pro** (2508.12631) | Test-time model router | embed query → k-means (k=60) → per-cluster accuracy/cost score → top-p nearest clusters → argmax of `α·perf + (1−α)·(1−cost)` | none (uses benchmark labels offline) |
| **Agent-as-a-Router / ACRouter** (2606.22902) | Online agentic router for **coding** tasks | Context→Action→Feedback→Memorize loop: contextual bandit + per-dimension priors + **embedding-kNN memory** of past outcomes | **yes** — Docker sandbox pass@1 on **provided/benchmark tests** + AST + self-consistency |

## How they map onto liccio

| External concept | liccio equivalent | Notes |
|---|---|---|
| Online feedback loop (C-A-F) | `RoutingDecision → attempt → compute_reward → bandit.observe_reward` | liccio already had it |
| Contextual bandit | `SimulatedBanditPolicy` (ε-greedy / Thompson, per-context arms) | same |
| Cost-aware reward `α·perf − cost` | `compute_reward` / `RewardWeights` (token-cost term); `finops.marginal_value` EMV; the α/ε dial | convergent |
| Verifier → score | auto-referee + battery (single-module); `swebench_referee` (repo-level) | liccio's is *fairer* (see below) |
| Per-cluster / per-task retrieval | **NEW: `acp.routing.memory_context.MemoryContext`** | the one thing liccio was missing |
| Static dimension priors | `capability_matrix` (per-cell evidence, Wilson CIs) | liccio's has honest small-sample handling |
| Champion/challenger rollout | `PolicyRegistry` | — |
| Escalation / cascade | `unified_router`, `topology_program_executor`, best-of-k | **liccio only** — the references route once, no escalation |

## What we adopted: embedding-kNN memory context

ACRouter's strongest, most transferable claim is empirical: coarse categorical context (liccio's
`task_type|risk_level`) captures only a fraction of the routing signal (~27% of oracle entropy in their
setup); the rest is in per-task content, recoverable by retrieving similar past tasks and their verified
outcomes. This is also the per-task-retrieval form of the "cluster-id as bandit context" idea we had
parked from the Avengers-Pro discussion — and kNN-over-an-outcome-store is a cleaner fit than k-means
(it slots straight onto the bandit as a cold-start prior and warm-starts from logged rewards).

Implemented in `acp.routing.memory_context` (commit on `claude/hopeful-carson-xEoNq`), **opt-in and
non-breaking**:

- `MemoryContext.add(task_text, action_key, reward, cost)` — FIFO-bounded (default 20k) online store
  keyed by a task embedding (reuses `acp.context.embeddings.Embedder`; `HashingEmbedder` default, no
  deps; voyage/sentence-transformers/OpenAI plug in via the same protocol).
- `MemoryContext.query(task_text) → NeighborContext` — cosine-kNN (k=10, threshold 0.5) → per-action
  mean reward / counts / best action; `sparse` when nothing clears the threshold.
- `RoutingFeatureExtractor.extract(..., memory=None)` — when a memory is supplied and neighbours are
  non-sparse, adds `neighbor_count` / `neighbor_action_reward` / `neighbor_best_action`. **`context_key`
  is unchanged**; absent/sparse memory adds no keys.
- `SimulatedBanditPolicy` seeds **cold** arms (n==0) from `neighbor_action_reward` (logistic-squashed
  into the arm mean-proxy space). Tried arms and the no-memory path are byte-for-byte unchanged.

To use it: construct one `MemoryContext`, pass it to `extract(..., memory=m)`, and call `m.add(...)`
after each verified outcome. With no memory wired in, routing is exactly as before.

## Should we "just use theirs"? No.

- **Weave**: ELv2 license (anti-competing-product) + a Go per-request proxy is the wrong altitude and a
  breaking interface swap; liccio routes per *task* among agents with escalation + verification.
- **Avengers-Pro / ACRouter**: research artifacts, not drop-in libraries; liccio already has the
  architecture. We took the one missing idea (memory) and reimplemented it in-tree.

## The honest caveat that ties to liccio's hardest open problem (W4)

All three reference verifiers are reliable **by assumption**: Avengers-Pro uses offline benchmark labels;
ACRouter uses **provided/benchmark test cases + a Docker sandbox** (pass@1). That is exactly the *oracle
stop* liccio's P9 already showed works. liccio's frontier (P10–P12, `swebench_referee`) is the **fair**
case: in production the router/verifier does **not** have the held-out tests (using them is cheating), so
it must *synthesize* the correctness signal — and the W4 pilot measured that synthesis to be the
bottleneck (repro-quality-bound; precision is solid at false-commit 0, recall is noisy). So ACRouter's
headline ("execution-grounded feedback closes the routing gap") is true *when you can trust the
verifier*; making a verifier trustworthy **without** the held-out tests is the real work, and these
papers don't address it. If anything they are evidence that liccio's investment in a *fair* verify
signal is aimed at the right, harder target.

## One-line takeaways

- Online + execution-grounded + cost-aware routing is the right shape — three independent efforts agree,
  and liccio already built it.
- Per-task embedding-kNN memory beats coarse categorical context; now in-tree (`memory_context`),
  opt-in, non-breaking.
- liccio is ahead on escalation/cascade and on *fair* verification; the references assume a trustworthy
  verifier that production routing does not get for free.
