# Cross-Harness Routing — can we route across agent harnesses, not just LLM models?

**Date:** 2026-06-07 · **Live this run:** Anthropic (single-shot + in-process tool-loop harness) and
Google Gemini (the real `gemini` CLI agent, and OpenHands V1 backed by Gemini). The hetero round
routed across **LLM models** (single API calls). This round routes across **agent harnesses** — the
autonomous, stateful, tool-using *scaffolds* that wrap a model and let it explore a repo and run
commands. Same tasks, same held-out hidden-test verifier; the only thing that changes is the harness.

> **Is routing across harnesses/CLIs possible?** Yes — and it already shares the model-routing
> machinery. Every adapter (single-shot model or full harness) implements one `AgentAdapter`
> protocol (`src/acp/agents/base.py` → `execute() → AgentAttemptResult`), so a harness and a model
> call are interchangeable in the same routing/scoring code.

## The harnesses routed across

| Policy | Harness type | Model | Live here |
|---|---|---|---|
| `single_shot` | none — one API call, minimal context | claude-sonnet-4-6 | ✅ |
| `inproc_harness` | ACP's in-process tool loop (read/write/run) | claude-sonnet-4-6 | ✅ |
| `gemini_cli` | Google's real `gemini` CLI agent (autonomous) | gemini-2.5-flash | ✅ (sandboxed) |
| `openhands` | OpenHands V1 **local-runtime** agent (no Docker) | gemini-2.5-flash | ✅ (sandboxed) |
| `claude_code_cli` | Anthropic's Claude Code CLI | claude | ❌ see below |

**Claude Code CLI** is installed (`v2.1.168`) but **unrunnable in this sandbox**: its binary sits
behind a **read-only `700 root`** mount, so no non-root user can reach it, and the CLI **refuses
`--dangerously-skip-permissions` as root**. It is represented on the harness axis by the in-process
Claude tool-loop harness (same model family, real tool loop).

## Live bring-up: what it took to route across real CLI agents (honest engineering log)

Spawning autonomous CLI agents is exactly the "create unsafe agents" category, so this ran **only
under explicit user authorization**, with the agents confined to the non-root `claude` user, inside
throwaway temp-dir fixtures, with secrets scrubbed from captured output. Obstacles found and fixed:
- **Egress is a TLS-intercepting proxy.** The sandbox user's Node died with
  `SELF_SIGNED_CERT_IN_CHAIN` until `NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt` (the
  egress-gateway CA) was passed through. (curl worked, masking it — only Node's `fetch` tripped.)
- **Gemini CLI workspace trust:** headless runs refuse to act unless `GEMINI_CLI_TRUST_WORKSPACE` /
  `--skip-trust` is set.
- **Ancestor traversal:** Python's `TemporaryDirectory` is `700 root`; the agent (uid 999) couldn't
  `realpath()` its own workspace (`EACCES`) until the whole ancestor chain was opened for traverse.
- **OpenHands without Docker:** the Docker daemon **can** be started here (vfs driver, `--iptables=false`),
  but the **image registry is allowlist-blocked**, so the Docker runtime has no image. OpenHands V1's
  **`LocalWorkspace` local runtime** sidesteps Docker entirely and runs the agent's terminal/editor/grep
  tools on the host — that is what made OpenHands live (backed by Gemini via litellm).

## Experiment 1 — capability corpus (control): is a harness overkill on well-specified tasks?

6 self-contained bugfixes, hidden-test verified (n=6/policy, 24 live cells):

| Policy | verified | 95% CI | cost/success | avg latency |
|---|---|---|---|---|
| **single_shot** | **1.00** | [0.61, 1.00] | **$0.0031** | **4s** |
| gemini_cli | 1.00 | [0.61, 1.00] | (tokens n/a) | 42s |
| openhands | 1.00 | [0.61, 1.00] | $0.0275 | 62s |
| inproc_harness | 0.83 | [0.44, 0.97] | $0.0479 | 10s |

**Finding:** on well-specified tasks every harness matches a single model call (~1.00), but at
**10–15× the latency and cost** — and the in-process harness was actually *less* reliable (0.83;
one tool-loop slip). **A harness is pure overkill here** — the cost-rational policy is the single
call. (This mirrors the hetero round's "use the cheap lever when it suffices.")

## Experiment 2 — ceiling corpus (the money shot): does harness *autonomy* rescue context-gated tasks?

8 cross-file tasks where the fix depends on a constant in an **unreferenced** file — a single-shot
call with minimal context cannot see it. Hidden-test verified (n=8/policy, 32 live cells):

| Policy | verified | 95% CI | cost/success | avg latency | beats single-shot (CI) |
|---|---|---|---|---|---|
| **single_shot** (control) | **0.00** | [0.00, 0.32] | — | 6s | — |
| inproc_harness | 0.88 | [0.53, 0.98] | $0.0410 | 9s | ✅ |
| **gemini_cli** | **1.00** | [0.68, 1.00] | (tokens n/a) | 38s | ✅ |
| **openhands** | **1.00** | [0.68, 1.00] | $0.0188 | 45s | ✅ |

**Finding — harness autonomy is a real lever.** The single model call fails **every** task (0/8): the
answer is in a file minimal context never shows it. **All three autonomous harnesses beat it with
non-overlapping confidence intervals** — they `grep`/read the repo and *discover the file themselves*.
The two real CLI agents nailed every task (8/8); the lighter in-process harness got 7/8 (it gave up
without exploring on one — `xfileNG_scale_0`, returning in 3s). Per task, single-shot is a clean 0
across the board while the CLI agents are a clean 1.

This is the harness-side analogue of last round's result: there, an **orchestrated context-router**
hit 1.00 by *handing* the model the right file; here an **autonomous harness** hits 1.00 by *finding*
it. Same outcome, different mechanism — and a different cost profile: the router was one cheap
injected call, the autonomous CLIs cost ~38–45s of exploration each.

## Synthesis

**Yes — you can route across agent harnesses/CLIs, it uses the same control plane as model routing,
and the harness choice genuinely matters.** The two experiments bound *when*:

- **Well-specified tasks → the harness is overkill.** Every harness matched a single model call
  (~1.00) at **10–15× the latency/cost**, and the in-process harness was even slightly *less*
  reliable (more moving parts). Route to the single call.
- **Context-gated tasks → harness autonomy is a decisive lever.** A single call scores **0/8**;
  the autonomous CLI agents score **8/8** by exploring the repo to find what they were never handed,
  beating the baseline with CI separation. This is an *alternative to orchestrated context-routing*:
  last round a router hit 1.00 by injecting the right file; here the harness hits 1.00 by finding it
  — at a latency premium (~40s of autonomous exploration vs one cheap injected call).

So the metarouter's job extends cleanly from "pick the cheapest capable **model**" to "pick the
cheapest capable **harness**": a single call when the task is well-specified; an autonomous harness
when the task needs exploration the caller can't pre-orchestrate. Demonstrated live across two vendor
families (Anthropic + Google) and two real CLI agents (Gemini CLI + OpenHands), with OpenHands'
local runtime proving autonomous-harness routing works even with the Docker registry blocked.

## Honest limitations
- Small corpora (CLIs are slow) → n=6–8/policy, wide CIs (reported). A proof of concept, not a
  production benchmark.
- **Cost attribution for the Gemini CLI is n/a** (it doesn't emit token usage); latency carries its
  comparison. OpenHands and the API policies report real token cost.
- Claude Code CLI couldn't run here (read-only mount); the in-process Claude harness stands in.
- Autonomous CLIs ran under explicit authorization, sandboxed to a non-root user + temp dirs.

## Reproduce
```
uv run python -m evals.harness_arena.run --corpus capability --trials 1
uv run python -m evals.harness_arena.run --corpus ceiling --trials 1
```
Artifacts: `reports/harness_arena_capability.json`, `reports/harness_arena_ceiling.json`.
