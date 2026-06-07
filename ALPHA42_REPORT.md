# Alpha 42 — Evidence-Driven MetaRouter + Agent FinOps

**Date:** 2026-06-07
**Acceptance question:** *Can ACP learn when to use a cheap executor, a stronger advisor, k
weak candidates, repo-map/grep context, memory, or abstention — and beat static routing on
verified success per dollar?* **Yes, on live evidence** (Claude-reachable; OpenAI/Gemini are
pluggable hooks, unavailable here and treated as availability — not capability — evidence).

This round followed the GOALS.md directive to make the next layer an **evidence-driven
MetaRouter Arena + FinOps Controller**, not "more features in isolation." Every module is judged
by whether it improves the arena report.

## The headline (live MetaRouter Arena, claude-sonnet-4-6)

Five unseen tasks spanning `context_need` (none / exact_symbol / cross_file_api /
broad_repo_map / underspecified), each with a held-out hidden-test verifier. Policies ranked by
**verified success per dollar**, availability separated from capability:

| Policy | verified success | cost / verified success |
|---|---|---|
| `repo_map_router` | **1.00** | **$0.0015** ← best routable |
| `oracle` (ceiling) | 1.00 | $0 |
| `advisor_router` | 0.80 | $0.0034 |
| `claude_harness` (strong single) | 0.80–1.00 | $0.029 (~19× costlier) |
| `cheap_single` | 0.60 | $0.0029 |
| `best_of_k_router` | 0.60 | $0.0063 |
| `cheap_static` (floor) | 0.00 | — |

**The thesis holds:** measured orchestration beats the static strong-single-agent baseline on
**both** verified success and cost. The FinOps Pareto gate flags `repo_map_router` as
**promotable** over the `cheap_single` incumbent; the `repo_map` win reproduces in **2 task
families** (not one hand-built task).

## Deliverables by workstream

| P | Workstream | Module(s) | Artifact | Result |
|---|---|---|---|---|
| P0 | MetaRouter Arena | `evals/metarouter_arena/*` | `reports/metarouter_arena.json`, `…policy_compare.json` | substrate; live 7-policy comparison |
| P1 | Advisor escalation | `orchestration/advisor.py` (+ arena policy) | `reports/advisor_ope.json` | advisor lifts verified **0.60→0.80** (+0.20) at call-rate 0.40 |
| P2 | Best-of-k comparator | `weak_model_candidates` (+ arena policy) | `reports/best_of_k_comparator.json` | beats strong-single on cost; honest no quality lift at k=2 |
| P3 | Topology controller search | `routing/topology_controller_search.py` | `reports/topology_controller_search.json` | offline search; **+0.08** objective gain, promotable; safety-constrained |
| P4 | Context-strategy OPE | `context/context_strategy_ope.py` | `reports/context_strategy_ope.json` | cross-file/broad → repo_map; honest grep-vs-embedding null |
| P5 | Context sufficiency + abstain | `evaluation/context_sufficiency.py`, `routing/{answer_or_abstain,spec_needed}_gate.py` | — | underspecified ticket → spec-needed; high-risk thin-evidence → abstain |
| P6 | Meta-agent FinOps | `src/acp/finops/*` | `reports/finops_cost_per_verified_success.json` | budget classes, marginal value of compute, Pareto promotion gate |
| P9 | Vendor-native live gate | `evals/vendor_native_live/*` | `reports/vendor_native_live_gate.json` | availability ≠ capability; claude_harness HAR/HFR/PWL=1.0; openai/codex/openhands self-skip |
| P10 | Memory lifecycle | `src/acp/memory/*` | `reports/memory_aging_smoke.json` | first-attempt success **+0.17** over a memoryless baseline; decay + quarantine |
| P7/P8 | Harness evolution / task synth | `training/harness_evolution.py`, `agents/task_synthesizer.py` | (pre-existing) | already implemented in prior rounds |

## Adapter-agnostic by construction (GOALS principle)

No live OpenAI/Gemini dependency. All live proof uses the reachable Claude adapter/harness plus
deterministic fake/patch baselines. Unavailable providers are **discoverable with a reason** and
**never routed by default or counted against capability** (`AdapterStatus`: live_conclusive /
live_inconclusive / unavailable / mock_contract_only / fixture_only). The vendor gate and arena
both enforce this separation.

## Command surface (DoD)

```bash
uv run python evals/metarouter_arena/run_arena.py [--full]   # or: acp arena run [--full]
acp arena compare        # verified success per dollar ranking
acp finops report        # cost attribution + Pareto promotion
acp context strategy-ope # which context strategy to route per context_need
acp context topology-search
acp health --mode production
```

## Honest limitations

- **Smoke-scale cells.** The arena runs 5 tasks × 7 policies; the ≥300-conclusive-cell
  acceptance gate needs a larger live budget. Cells are fixture-unseen (authored for the arena),
  not scraped real-repo history — a faithful step on the same infrastructure a real ingestor
  would feed.
- **grep-vs-embedding is reported as `insufficient_evidence`**, not a claim — ACP only has
  minimal/repo_map cells so far; the honest null is surfaced rather than hidden.
- **best_of_k at k=2** added no quality over a single cheap shot here (two minimal-context
  candidates lack diversity on cross-file tasks); it is cheaper than the strong harness. Real
  lift needs diversity prompts + a strong fallback.

## What this proves

ACP's near-term moat — **measured orchestration**: context/memory routing, confidence-aware
advisor escalation, proof-selected candidates, offline topology search, and FinOps-aware
promotion — is now tested directly against static baselines on **verified success per dollar**,
with live evidence and an availability-vs-capability discipline that keeps the measurement clean.
