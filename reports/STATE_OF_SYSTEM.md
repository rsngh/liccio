# State of the system — honest scorecard

One authoritative summary of what this meta-router is, what's *measured* (not asserted), what works,
what doesn't, and what's worth doing next. All numbers are from real runs in this environment.

## What it is
A meta-router over a pool of coding agents. For a real bug-fix task (real GitHub issue→fix bundle,
graded by the repo's own held-out test) it runs a **cheapest-first escalation ladder with verify-stop**:
solution-cache → in-process repair → gemini_cli → claude_code → codex_cli, stopping at the first rung
whose output passes the repo's test. It learns per-`(repo_family, failure_signature)` which rung wins.

## The honest scorecard (measured)

| claim | evidence | verdict |
|---|---|---|
| Model-only hits a wall on real bugs | 3/17 (18%) across cheap+frontier, single-shot+harness | **solid** |
| Real coding agents break the wall | Codex 17/17, Gemini 16/17, Claude Code 15/17 (easy); 7–9/10 (hard) | **solid** |
| Cost-routing matches the best agent for less | escalation = best single agent's solve rate at **~30–37% lower cost**, invoking the strongest agent ~0–1× instead of every task | **solid — the core value** |
| ...but the cost win is CONDITIONAL | sensitivity sweep: +30% at realistic prior, +76% steep gradient, but **NEGATIVE for flat/shallow priors** (you pay for failed cheap attempts) | **refined — needs steep gradient or difficulty-skip** |
| Harder bundles separate the frontier | hard-10: inproc .2 / claude .7 / gemini .8 / codex .9; one bug no agent solves | **solid** |
| Ensemble adds coverage over the best agent | greedy: **Codex alone = the full union** (superset); +0 marginal coverage from others | **refuted — pool value is cost+robustness, not coverage** |
| Pool insures against unknown-best | expected union of a *random* single agent only 0.71; ~3 random agents to reach union | **solid** |
| Verify-stop is necessary | a public-only signal would auto-commit **24% wrong** fixes (108-grading audit) | **solid** |
| Solution memory frees recurrences | exact-recurrence replay **17/17 = 100%** at zero agent calls; ~50% workload cost saved at 50% recurrence | **solid (offline)** |
| Diagnosis hand-off lifts the union | flipped 1 Gemini miss; did **not** crack the universal-miss bug | **modest** |
| Boosted cheap repair (repair_v2) | hard cheap rung 2/10 → 3/10 (+1 feature-add), higher per-attempt cost | **modest** |
| Predictive (difficulty) routing | LOO at n=27: no zero-regret threshold; can't isolate the cheap-winnable minority | **negative — data-starved** |
| Test-time multi-sampling cracks the hardest bug | best-of-3 Codex partial (#0–7 single-shot); #8 resampling **not reached** | **open — environment-blocked** |

## What genuinely works (the value)
1. **Cost-routing economics** — ≥ best single agent on quality, < always-running-it on cost.
2. **The verifier** — the repo-test verify-stop is load-bearing and validated; public-only is unsafe;
   the patch-equivalence probe is too brittle to gate on (95% disagreement) → reporting-only.
3. **Solution/procedural memory** — exact recurrences become free verified solves (rung 0 of the router).

## What doesn't (yet), stated plainly
- Orchestration **cannot manufacture capability**: the cheap model stays ~18%, and one hard bug
  defeats the entire pool even with hints. The wall is model skill.
- The **learned** levers (difficulty routing) are data-starved at n≈27 — no usable signal.
- Diagnosis hand-off and boosted cheap repair help at the margins, not the ceiling.

## Architecture map
- `src/acp/routing/unified_router.py` — route_and_solve: solution-cache rung 0 → memory-reorder →
  FinOps trim → safety-bounded escalation (`topology_program_executor`) → learn. Agent-swap ladder via
  `build_agent_ladder` / `make_agent_attempt_fn`.
- `src/acp/memory/` — `experience_bank` (which rung won/failed) + `solution_store` (cache+replay fixes).
- `src/acp/verification/` — verify-stop, proxy/independent checks, safety invariants.
- `src/acp/routing/difficulty_probe.py` — predictive routing (infra; needs more data).
- `evals/issue_replay/` — corpus build/harvest (flat + package mode), live runner, escalation
  economics, multisample, verifier audit, solution-memory + predictive evals.

## Environment constraints (operational reality)
- Detached/background jobs do **not** survive idle-suspend; foreground Bash caps at 10 min. All work
  must be bounded, incrementally persisted, and committed every increment (pushed branch = only store).
- No GitHub API (clone-only). Gemini live; Codex/Claude on subscription ($0 metered).

## What to try next (ranked, with the constraints in mind)
1. **Verifier-guided multi-sampling on strong agents** — the only lever with a shot at the ceiling;
   needs a background-capable runner (blocked here by suspend). Highest upside.
2. **Scale the corpus to ~100+ bundles** — the binding constraint on every learned component; the
   resumable harvester now supports it, but yield is repo-dependent (more-itertools-class repos work;
   data-file/complex-import repos don't).
3. **Solution-memory in production loops** — biggest realistic payoff (repeated work on one codebase).
4. **Harden the verifier's blind spot** — independent fresh-test gate for high-stakes commits.
