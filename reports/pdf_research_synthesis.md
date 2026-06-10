# PDF research synthesis → three prongs to drive repair/routing performance

Read all 58 papers in `pdfs/` (agents & harnesses; memory & context). They converge on a small set
of *cheap, implementable* mechanisms aimed squarely at this project's three **measured** bottlenecks:

- **(a) "right function, wrong fix"** — the cheap in-process rung locates the buggy function but
  writes a wrong patch ~80% of the time (`issue_replay_diagnosis.json`).
- **(b) no shared diagnosis** — on the hard bundles the union of *all* agents is 9/10; independent
  attempts never learn from each other.
- **(c) blind cheapest-first** — every hard task still pays for a doomed cheap attempt first.

## What the literature converges on (and where we used it)

| mechanism | papers | prong |
|---|---|---|
| rationale / API-map context (not just the isolated function) | RepFuse 2402.14323, aider repo-map, GraphCoder 2406.07003 | A |
| learn from failed attempts (verbal reflection in the prompt) | Reflexion 2303.11366, GEPA 2507.19457 | A |
| proposer / **critic** separation; committee boosting | MAR 2512.10696, Boosting-weak-reasoners 2605.14163 | A, B |
| early prune of un-parseable / duplicate candidates before paying to test | VerMCTS 2402.08147 | A |
| **shared artifacts / diagnosis hand-off** across agents | SDB 2605.20173, Code-as-Harness 2605.18474 | B |
| difficulty / sufficient-context prediction before acting | Sufficient-Context 2411.06037, MetaCogAgent, Efficiency-Frontier 2605.23071 | C |
| grep+repo-map beats heavy semantic RAG for code | "Is grep all you need" 2605.15184, aider/llamaindex/doug write-ups | A (context) |
| procedural / distilled experience reuse (beyond meta-only memory) | ReMe 2601.07190, Mem^2 2510.04618, ACE 2508.06433 | future |

## Prong A — boosted localized repair (`evals/issue_replay/repair_v2.py`, `--mode repair2`)
On top of v1's localize→splice: (1) module API-map + sibling signatures in the prompt; (2) failed
patches fed back as "do not repeat"; (3) a skeptic **critic** call between rounds that must state the
root cause, conditioning the next round; (4) AST-parse + AST-hash dedupe prune before any test run.
Targets bottleneck (a). Captured as **rung 1 of the live ladder** on the hard 10.

**Result:** the boosted cheap rung solved **3 of the first 9 hard bundles** (#3 running_statistics,
#5, #6) vs the v1 cheap rung's **2/10** on the same set (#5, #6 only). So +1 cheap solve — and the
flip is a *feature-add* bundle (#3) the v1 cheap rung never got. Modest but real, at higher
per-attempt cost (k=3 × 2 rounds + critic vs v1's k=1). n is tiny; the clean re-run adds #9.

## Prong B — live ladder with diagnosis hand-off (`evals/issue_replay/ladder_live.py`)
Runs the real verify-stop ladder inproc→gemini_cli→claude_code→codex_cli; when a rung fails, its
**capped patch diff + the test failure** are injected into the next rung's prompt. The P4 no-hint
per-agent vectors (gemini 8/10, claude 7/10, codex 9/10; union 9/10) are the ablation baseline.
Targets bottleneck (b).

**Result (bundles 0–8; the first run crashed on #8's hint-distillation via the now-fixed timeout
bug — these are the real logged rung outcomes, clean re-run in progress):**

- The hinted `gemini_cli` ran on the 6 bundles the cheap rung missed and solved 5 (#0,1,2,4,7).
  Crucially **#7 is a bundle no-hint Gemini MISSED in P4** (its vector `1111111001` fails #7,#8) —
  the failed cheap rung's diagnosis brief **flipped #7 for Gemini**. That is direct evidence the
  hand-off helps an agent solve a case it misses on its own.
- The one bundle still unsolved is **#8 "concurrent tee"** — the universal miss (every agent fails
  it in P4, with or without hints). So the hand-off did **not** raise the union ceiling (9/10);
  what it changed is that an agent solved *earlier/cheaper* than it would have alone.

**Honest verdict:** diagnosis hand-off is a real but **modest** lever at this n — it flipped one
Gemini miss and let the cheap rung clear three bundles, trimming escalations; it did not crack the
genuinely-hard bundle that defeats the whole pool. Worth keeping as a cheap mechanism; not a
ceiling-breaker.

## Prong C — predictive routing (`src/acp/routing/difficulty_probe.py`, `evals/.../predictive_routing.py`)
A tiny auditable logistic probe over intake-only features (module/test size, feature-add, package
shape) predicting whether the cheap rung is doomed, evaluated **leave-one-out**.

**Honest negative result (n=27):** 22/27 bundles are doomed for the cheap rung (81% base rate). A
threshold sweep finds **no** operating point that skips doomed attempts without losing easy wins —
intake-only features can't isolate the small cheap-winnable minority at this n (at 0.85 it saves 26%
cheap-cost but loses 2 of 5 easy wins). The probe + 3 unit tests ship as sound infrastructure; it
needs materially more labeled bundles or a cheap *dry-run* signal to become useful. Recorded in
`reports/issue_replay_predictive_routing.json` (`verdict: INSUFFICIENT SIGNAL`).

---

# Second wave (#1–#4): driving the ceiling, scaling data, memory, verifier trust

## #3 — procedural / solution memory (`src/acp/memory/solution_store.py`)
Beyond the outcome-only ExperienceBank: cache the **verified fixed function(s)** per
`(repo_family, failure_signature)` and **replay** them by AST-splice into the current buggy module.
A recurring bug (CI retry, reopened issue, regression) is then solved with **zero agent calls** —
splice + verify. Trust-gated (only verified fixes admitted), tenant-isolated, drift-safe (splice
returns `None` if the target function is gone → fall back to the live ladder). 4 unit tests. This is
the research's "store solutions, not just outcomes" idea (Mem²/ReMe/ACE), and it targets the
realistic deployment: repeated work on one codebase.

## #4 — verifier reliability audit (`evals/issue_replay/verifier_audit.py`)
Everything rests on one signal — "repo test passed → commit." Audited across **108 real candidate
gradings** (4 agents × easy+hard):

- **Public-only is unsafe:** it would auto-commit **24 hidden-failing fixes (24% of its accepts wrong)**.
  The held-out repo-test verify-stop is necessary, not optional — this validates the core design.
- **The patch-equivalence probe is too brittle to gate on:** it disagrees with the repo test on
  **73/77 (95%)** of *correct* fixes; as a commit gate it would reject nearly everything real.
- **Recommendation:** keep the repo test as the primary verify-stop; for high-stakes commits add an
  **independent freshly-generated check** (`verification.proxy_stop_signal` / `independent_proof`) —
  *not* the probe; demote patch-equivalence to a reporting-only diagnostic.

## #1 — verifier-guided multi-sampling on a strong agent (`evals/issue_replay/multisample.py`)
Best-of-N on a single strong agent (Codex), N independent runs, verifier-selects the first that
passes the held-out test. Tests the research's coverage-scaling claim and, specifically, whether it
cracks the universal-miss bundle (#8 "concurrent tee") that defeated the whole pool. _Result: pending
the live run (best-of-3 Codex on the hard 10)._

## #2 — corpus scaling (`evals/issue_replay/build_real_corpus.py`)
Added jmespath + arrow as package-mode repos (on top of toolz/more-itertools/parse/boltons/stringcase)
to grow the labeled set toward the ~100+ bundles the learned components (routing, difficulty, memory)
need for signal — the binding constraint behind #C's negative result. _Result: build in progress
(writes `real_issue_replay_full_v2.json`)._

---

# Round 2 results + environment lesson

## ENVIRONMENT CONSTRAINT (learned the hard way)
Detached/background jobs do **not** survive this container's idle-suspend: the #1 multisample and #2
corpus builds were silently killed ~95 min in (no Python procs, frozen logs, no completion markers),
and #2's full file — written only at the end — was lost (40 harvested bundles gone). Foreground Bash
also caps at 10 min. **Strategy going forward:** bounded (<~8 min) work units that persist
incrementally and commit+push every increment (the pushed branch is the only durable store);
long experiments must be resumable and run in slices, never as fire-and-forget background jobs.

## #1 — multi-sampling (PARTIAL, job killed)
Best-of-3 Codex reached 8/10 before the container killed it: bundles #0–7 each solved on the FIRST
sample (best-of-{1,2,3} all = 8, no resampling needed). The decisive test — does resampling crack the
universal-miss #8 — was **not reached** (#8 sample 1 failed; samples 2–3 and #9 never completed).
Open question; must be re-run as a bounded slice (just #8/#9).

## #3 — solution-memory payoff (`evals/issue_replay/solution_memory_eval.py`) — STRONG
Offline, on the real easy-17: store the gold fix, then replay it on a recurrence and grade with the
pristine held-out test (zero agent calls).

- **Exact recurrence: 17/17 = 100%.** An identical re-encounter (CI retry, regression of the same
  bug) is solved by returning the verified module verbatim — free. (Added an exact buggy-fingerprint
  match path to `SolutionStore`; function-splice remains the ~41% best-effort path for *drifted*
  modules, where the fix touches more than one function body.)
- **Cost model:** avoided ladder cost scales linearly with recurrence — at 50% recurrence, **50% of
  total workload cost** is saved. This is the clearest payoff yet for the realistic deployment
  (repeated work on one codebase), and it needs no model capability gain at all.
