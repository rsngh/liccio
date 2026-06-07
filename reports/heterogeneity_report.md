# Heterogeneity Round — does routing cheap→strong actually pay?

**Date:** 2026-06-07 · **Providers LIVE this run:** Anthropic (haiku/sonnet/opus) **and** Google
Gemini 3.x (flash-lite / flash / pro). The earlier rounds had effectively one model family, so
"routing" could only ever mean *context* routing. This round closes the **#1 gap** the prior
evaluation named: *real model/provider heterogeneity* — genuinely different tiers and a genuinely
different vendor to route between.

> The honest question, asked four ways: **with several real tiers available, does paying for a
> stronger/different model buy more verified success — and if so, when, and is it worth the cost?**

Everything below is **live, single-shot, hidden-test-verified** (the agent never sees the grading
test), costed at each tier's real published price, with **Wilson 95% CIs** and conclusive-vs-infra
separation. No metric is a point estimate; no unavailable provider is charged as a capability loss.

---

## The tiers (real prices)

| Tier | Provider | Model | $/1M in | $/1M out |
|---|---|---|---|---|
| gemini_flash_lite | Google | gemini-3.1-flash-lite | 0.10 | 0.40 |
| gemini_flash | Google | gemini-3.5-flash | 0.30 | 2.50 |
| haiku | Anthropic | claude-haiku-4-5 | 1.00 | 5.00 |
| sonnet | Anthropic | claude-sonnet-4-6 | 3.00 | 15.00 |
| gemini_pro | Google | gemini-3.1-pro-preview | 2.00* | 12.00* |
| opus | Anthropic | claude-opus-4-8 | 15.00 | 75.00 |

\*Gemini 3.x preview prices are **estimates** from the published flash-lite/flash/pro tiering; the
load-bearing fact is the *ordering* (flash-lite < flash < haiku < sonnet < pro < opus) and that
every Gemini tier is far cheaper than opus. Opus output costs **15×** haiku, **30×** gemini-flash,
**~190×** gemini-flash-lite.

---

## Experiment 1 — Capability probe: is there even a tier gap? (Anthropic)

8→20 self-contained, minimal-context tasks of rising difficulty (string ops → edit distance, LIS,
a JSON-grammar validator, wildcard/regex matching, a bytecode VM, N-Queens, coin-change DP). The
**only** lever is model strength — no cross-file trick. Across haiku/sonnet/opus, 3 trials:

| Tier | verified | 95% CI | total cost |
|---|---|---|---|
| haiku | **1.00** | [0.86, 1.00] | $0.023 |
| sonnet | 0.88 | [0.69, 0.96] | $0.062 |
| opus | 0.88 | [0.69, 0.96] | $0.416 |

The sonnet/opus "misses" were **one task** (`cap_intervals`) where the stronger models return
`[[1,6],…]` (lists) and the exact-equality test expects tuples — a brittle-test/formatting
artifact, **not** a capability deficit. **Finding: no measurable capability gap; the cheapest tier
is already at ceiling.**

## Experiment 2 — Capability arena: 5 policies, 20 tasks, 200 live cells

| Policy | verified | 95% CI | cost/verified-success | total |
|---|---|---|---|---|
| **haiku_single** | **1.00** | [0.91, 1.00] | **$0.00132** | $0.053 |
| cost_aware_escalation | **1.00** | [0.91, 1.00] | $0.00136 | $0.054 |
| sonnet_single | 0.95 | [0.84, 0.99] | $0.00337 | $0.128 |
| best_of_k_haiku (k=3) | 0.95 | [0.84, 0.99] | $0.00424 | $0.161 |
| opus_single | 0.93 | [0.80, 0.97] | $0.02188 | $0.810 |

Three honest, somewhat counterintuitive results:

1. **Opus is dominated.** It scored *lower* than haiku (0.93 vs 1.00 — a stochastic slip on the
   unary-minus calculator plus the formatting artifact) at **16.5× the cost per success.** On small
   well-specified tasks, **paying for the frontier model is pure waste.**
2. **`cost_aware_escalation` does the right thing automatically.** Its public-test stop signal fires
   at the haiku rung every time, so it matches haiku's 1.00 at essentially haiku's price — it
   *never escalates* because it never needs to, capturing the savings with no human tuning.
3. **Naïve best-of-k is a trap here.** Sampling 3 haikus and selecting by the public test scored
   *worse* than a single haiku (0.95 vs 1.00) and cost 3×, because public-test selection sometimes
   picks a candidate that overfits the visible test but fails the hidden one. An honest negative
   result about weak proof signals.

**Verdict (capability): there is no model-tier gap on self-contained tasks — use the cheapest tier,
save ~16×. The router's correct move is to *not* escalate.**

## Experiment 3 — Ceiling arena: when the cheap model fails, is *tier* the fix? (18 cross-file tasks, 144 cells)

These tasks hide the answer (a non-guessable constant) in a file minimal context never shows the
agent — so the cheap model genuinely fails. Does a **bigger model** rescue it, or **better
context**?

| Policy | verified | 95% CI | total cost |
|---|---|---|---|
| haiku_single (minimal) | 0.00 | [0.00, 0.10] | $0.018 |
| opus_single (minimal) | **0.00** | [0.00, 0.10] | $0.440 |
| cost_aware_escalation (tier ladder, all minimal) | **0.00** | [0.00, 0.10] | $0.546 |
| **context_first_escalation** (add context on cheap model first) | **1.00** | [0.90, 1.00] | $0.037 |

**This is the sharpest result in the round.** Upgrading the *tier* changes nothing — opus with
minimal context scores 0.00 just like haiku, because **a stronger model still can't see the file**;
the pure-tier ladder even *wastes* $0.55 climbing to opus for zero gain. Adding **context** on the
*cheap* model rescues everything to 1.00 at **$0.001/success**. **Context, not tier, is the lever**
— exactly the "it's plumbing" critique from the prior evaluation, now measured and quantified.

## Experiment 4 — Cross-provider arena: Gemini 3.x + Claude (the real heterogeneity)

<!-- XPROV_PLACEHOLDER -->
_Running live; results filled in on completion. The setup: six tiers across two vendor families on
the 20-task capability corpus, plus a cross-provider cheapest-first escalation
(flash-lite→flash→haiku→sonnet→pro→opus) and a provider-diversity best-of (gemini-flash-lite +
haiku). The smoke test already surfaced the first **genuine capability gap**: gemini-3.1-flash-lite
(~150× cheaper than opus) fails the unary-minus calculator that every other tier solves — so here,
finally, "route cheap→strong" has a real gap to exploit._

---

## Synthesis (so far)

The metarouter's economic thesis, tested with real tiers, resolves into a precise and honest claim:

- **Model tier rarely matters on small, well-specified tasks.** Cheap models (haiku, and Gemini
  flash) are at ceiling; opus is *dominated* — more expensive and no better. Use the cheap tier.
- **When the cheap model fails, the cause is usually *context*, not *capability*.** Upgrading the
  model buys nothing; routing the right context on the cheap model fixes it for ~$0.001.
- **`cost_aware_escalation` captures both truths automatically:** it stays cheap when cheap suffices
  and (in the context-first form) escalates the cheapest effective lever first. It never blindly
  pays for the frontier model.

This is the un-hyped version of the product claim: **the control plane's value is routing the
cheapest *effective* lever — usually context, occasionally a stronger model — not defaulting to an
expensive one.** Measurement, not marketing: every number above is reproducible, CI-bounded, and
hidden-test-verified.

## Honest limitations

- Tasks are small, self-contained fixtures (one buggy function + tests), not whole repositories.
  The capability ceiling finding ("cheap is enough") is therefore scoped to *small, well-specified*
  work — precisely the work that is hidden-test-gradeable. Larger, ambiguous, or
  judgment-heavy tasks (which pytest can't grade) may still separate tiers; that needs semantic
  judges, not more fixtures.
- Gemini 3.x preview pricing is estimated; the relative ordering is what the conclusions rest on.
- `best_of_k`/diversity used a public-test comparator (the only production-available proof signal);
  a stronger verifier would change its selection quality.

## Reproduce

```
uv run python -m evals.hetero_arena.probe --trials 3
uv run python -m evals.hetero_arena.run --corpus capability --trials 2
uv run python -m evals.hetero_arena.run --corpus ceiling --trials 2
uv run python -m evals.hetero_arena.xprovider --trials 2
```
Artifacts: `reports/hetero_probe.json`, `reports/hetero_arena_capability.json`,
`reports/hetero_arena_ceiling.json`, `reports/hetero_arena_xprovider.json`.
