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
<!-- INC2 -->

## Increment 3 — Self-tuning ladder learned offline from traces
<!-- INC3 -->

## Increment 4 — Self-evolving context + verification for non-test tasks
<!-- INC4 -->

## Reproduce
```
uv run python -m evals.harness_router.run --tasks 8
```
