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
Targets bottleneck (a). _Result: pending the live run (captured as ladder rung 1)._

## Prong B — live ladder with diagnosis hand-off (`evals/issue_replay/ladder_live.py`)
Runs the real verify-stop ladder inproc→gemini_cli→claude_code→codex_cli; when a rung fails, its
**capped patch diff + the test failure** are injected into the next rung's prompt. The P4 no-hint
per-agent vectors (gemini 8/10, claude 7/10, codex 9/10; union 9/10) are the ablation baseline.
Targets bottleneck (b). _Result: pending the live run._

## Prong C — predictive routing (`src/acp/routing/difficulty_probe.py`, `evals/.../predictive_routing.py`)
A tiny auditable logistic probe over intake-only features (module/test size, feature-add, package
shape) predicting whether the cheap rung is doomed, evaluated **leave-one-out**.

**Honest negative result (n=27):** 22/27 bundles are doomed for the cheap rung (81% base rate). A
threshold sweep finds **no** operating point that skips doomed attempts without losing easy wins —
intake-only features can't isolate the small cheap-winnable minority at this n (at 0.85 it saves 26%
cheap-cost but loses 2 of 5 easy wins). The probe + 3 unit tests ship as sound infrastructure; it
needs materially more labeled bundles or a cheap *dry-run* signal to become useful. Recorded in
`reports/issue_replay_predictive_routing.json` (`verdict: INSUFFICIENT SIGNAL`).
