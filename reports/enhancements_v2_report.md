# Enhancements v2 — research-grounded, measured (4 increments)

**Date:** 2026-06-07. Grounded in the pdfs/ research (titles read directly via locally-installed
`pypdf`) + the measured gaps. Disciplined measurement throughout: Wilson CIs, availability ≠
capability, conclusive-vs-infra separation, all cost charged (thinking + verifier tokens).

---

## Increment 1 — Full lever matrix: model × thinking level × harness (Codex + OpenHands as options)

*Papers: Code as Agent Harness (2605.18747); Is Grep All You Need? (2605.15184); Deep Think with
Confidence / DeepConf (2508.15260); Boosting Weak Reasoning Models (2605.14163).*

The router now escalates across **four dimensions**, not just model+context:
1. **model family/size** — gemini flash-lite/flash, claude haiku/sonnet/opus;
2. **thinking level (new)** — explicit thinking-token budgets as escalation rungs *between* tiers
   (Claude extended-thinking + Gemini thinking; both verified live, thinking tokens billed);
3. **harness-aware context (new)** — autonomous CLIs get minimal injected context (they explore),
   single-shot gets repo_map;
4. **harness** — single-shot, in-process Claude loop, and the real autonomous agents.

**Vendor levers are availability-gated (never faked):**

| Lever | Status here | Reason |
|---|---|---|
| `gemini_cli` | **LIVE** | ok |
| `openhands` | **LIVE** | ok (local runtime, no Docker) |
| `codex_cli` | UNAVAILABLE | codex binary not installed (+ OpenAI network-blocked) |
| `claude_code` | UNAVAILABLE | binary behind read-only 700-root mount; refuses skip-perms as root |

Codex and Claude Code are **registered as real levers** (`acp.agents.sandbox_cli`, with correct argv,
sandbox, cost priors, and an env-aware healthcheck) — they activate with no code change the moment
the environment allows; here they report `UNAVAILABLE` and the router skips them.

**Live result (8 tasks, mixed + cross-file):** router verified **1.00** (CI [0.68, 1.00]) at
**$0.0021/verified-success**. Lever usage: `gflash_lite_min` 8 → `haiku_min` 5 → **`gflash_think_min`
4** → `haiku_repomap` 4. The router **tried a thinking rung before upgrading the tier**, and reached
repo_map only for cross-file tasks; the autonomous CLIs and opus weren't needed (cheap rungs
sufficed) — and the unavailable levers were skipped cleanly. **DeepConf** (`confidence_pruning`) is
wired into selection via `comparator_strength.deepconf_select` (prunes low-confidence candidates
*before* the expensive proxy checks; offline-tested).

*Answers the user's question directly: the router now routes across the CLIs and across thinking
levels — with Codex/Claude Code as honest, availability-gated options.*

---

## Increment 2 — Memory that survives repo evolution + reusable procedures

*Papers: AgingBench (2605.26302); Learning to Forget (2603.14517); Memp procedural memory
(2508.06433); Remember-Me-Refine-Me (2512.10696).*

Today's `avoid_strategies` is "ever-failed" — once a lever fails a signature it's banned forever, and
decay is never applied. After a repo evolves *back* (or a failure was transient), the again-good
lever can never be re-used (revision aging). `src/acp/memory/memory_revision.py` adds: **recency/
decay-aware** recommend+avoid (decide from the *net decayed reward*, so old failures age out), a
**sleep-style consolidation** pass (dedup conflicting episodes), and **procedural memory** (store the
winning lever *sequence*, not one strategy). `route_and_solve` accepts `recommend_fn`/`avoid_fn` to
plug these in.

**Deterministic migration benchmark** (one signature; good lever = `ctx` → migrates to `strong` at
session 4 → back to `ctx` at session 8). Post-back-migration (sessions 8+):

| Router | solved | avg cost/session |
|---|---|---|
| memoryless | 4/4 | $0.0040 |
| memory (ever-failed) | **3/4 — regresses** | $0.0080 |
| **memory + aging** | **4/4 — recovers** | **$0.0033** |

**Aging memory is both the most reliable and the cheapest after the migration-and-back**, because
old failures age out and the again-good lever is re-used. **Naive "ever-failed" memory regresses
(3/4) and costs more** — it permanently banned the now-good lever. This is the robustness the Phase-2
longitudinal win needs to survive an evolving repo.

## Increment 3 — Self-tuning ladder learned offline from traces

*Papers: AutoTTS / LLMs-Improving-LLMs (2605.08083); GEPA (2507.19457); Meta-Harness (2603.28052).*

The hand-tuned lever priors are a guess. `src/acp/routing/learned_ladder.py` learns, per
failure-signature, the lever order that minimizes expected cost-to-verified-success from logged
`(signature, lever, solved, cost)` traces (AutoTTS controller search — no RL training). Unlike online
memory (which warms up per deployment), this is batch-learned and fixed/auditable at deploy.

**Benchmark** — three families needing different levers (sigA→cheap, sigB→ctx, sigC→strong); learn
offline, evaluate on held-out tasks vs the hand-tuned global ladder:

| Router | solved | cost/verified-success |
|---|---|---|
| hand-tuned global (escalate from scratch) | 12/12 | $0.01033 |
| **offline-learned per-signature ladder** | 12/12 | **$0.00833** |

Learned ladders: `sigA→[cheap]`, `sigB→[ctx]`, `sigC→[strong]`. Same 100% success, **19.4% cheaper**
— it starts at the historically-best rung and skips the escalation warm-up (the residual cost is the
strong lever's own price on the genuinely-hard family, which any router must pay).

## Increment 4 (frontier) — Self-evolving context + verification for non-test tasks

*Papers: Agentic Context Engineering (2510.04618); Evaluating AGENTS.md (2602.11988); Sufficient
Context (2411.06037).*

- **Self-evolving repo playbook** (`src/acp/context/repo_playbook.py`): the router distils verified
  fixes into short per-repo lessons (an auto-maintained AGENTS.md), bounded and pruned (keep
  high-support/recent — the AGENTS.md study's caution that bad context hurts), rendered as a context
  preamble that surfaces the signature-relevant lesson first. Ties memory → context.
- **Calibrated stop** (`src/acp/verification/calibrated_stop.py`): for work hidden tests can't grade,
  commit only if a judge confidence clears a risk-calibrated bar AND context is sufficient
  (Sufficient Context: confident-but-wrong is the failure mode) — else abstain / human-review.

**Measured (deterministic policy benchmarks):** the playbook accumulates all signatures and surfaces
the correct lesson first (**relevant-first precision 1.0**); the calibrated stop committed 2/5 cases
with **zero confident-but-wrong commits** — it abstained on the weak/insufficient/high-risk-below-bar
ones (trades coverage for precision). *Honest limit:* the live solve-rate uplift from injecting the
evolved playbook into a model needs real calls; what's measured here is the policy (accumulation +
precision, and calibrated no-false-commit), not a live model improvement.

---

## Bottom line

Four research-grounded increments, each shipped with disciplined measurement:
1. **Router now spans model × thinking-level × harness** — Gemini CLI + OpenHands live, Codex +
   Claude Code registered & availability-gated; escalates thinking before tier (8/8 @ $0.0021).
2. **Memory survives repo evolution** — aging-aware revision recovers 4/4 after a migration-and-back
   at lowest cost, where naive memory regresses (3/4).
3. **Self-tuning ladder** — offline-learned per-signature order, 19.4% cheaper at equal success.
4. **Self-evolving context + calibrated abstention** — playbook precision 1.0; zero confident-but
   -wrong commits on non-test tasks.

Honest limits throughout: corpora are synthetic / policy benchmarks are deterministic where live
model noise would obscure the mechanism; Codex/Claude Code are env-gated; the playbook's live uplift
is deferred to model-call budget. All four advance the *mechanism* of performance/value, grounded in
the pdfs/ research.

## Reproduce
```
uv run python -m evals.harness_router.run --tasks 8
```
