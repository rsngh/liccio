# "Not Done" List — Closure Report

Response to the honest gap list. Each item verified against the current branch.

## Live-execution / environment-gated

- **WS14 — End-to-end live multi-task bakeoff — CLOSED (the most important miss).**
  Ran `run_live_bakeoff` live (ACP_OPENAI_API_KEY): **104 attempts** across 13 no-patch
  tasks × 2 reps × 4 adapters. Real tool-loop harnesses: **openai_harness 25/26,
  claude_harness 22/26**; fake/patch floor baselines. The capability matrix now carries
  **16 real-agent cells** (openai_harness/claude_harness, HAR=1.0) and the OPE log is over
  104 **observed** runs — routing/OPE/Pareto are no longer driven by the fake adapter.
  `measurement_hygiene/quality` + `tool_activation` regenerated from the real attempts
  (solve_rate 0.9038; outcomes incl. 2 correctly-classified harness_activation_failures).

- **WS18 — Docker live-security gate — VERIFIED.** Docker is present (intermittent under
  WSL2 load). Captured a fresh **9/9 checks pass** run; committed `docker_security_live.json`
  shows `passed=true`. The daemon flicker is handled: mid-run loss returns a clean **skip**,
  not a failure (measurement-trust).

- **WS19 — Vendor-native harness live gate — GREEN.** `vendor_harness_live.json`:
  `passed=true, n_solved=2` (codex_cli + claude_code solve; openhands health-checked).
  openhands argv None-guard is typed (mypy clean). Manifest-registered.

- **WS6 — Vendor harness live campaign — DONE (activation-aware).** `vendor_capability_matrix`
  runs Claude Code across the full graded+hard corpus; the run is activation-aware so a
  degraded CLI (no-op) is infra, not a capability/skill failure.

- **WS15 — Local LoRA pilot — N/A.** No torch/peft/GPU in this environment; legitimately
  skipped (reported, not overclaimed).

## Product / operator surface

- **Report warehouse — ALREADY PRESENT.** `acp reports ingest|list|show|diff` persist
  artifacts as DB-queryable Report entities (verified: ingested 87 entities). A duplicate I
  started was reverted once the existing implementation was found.

- **Operator surface** — CLI cockpit is substantial: `acp health --mode`, `acp evidence-gaps`
  (what to test next), `acp skill dashboard`, `acp reports list/show/diff`,
  `acp policy dossier`. A web UI is out of scope for this environment.

## Evidence-quality caveat — ADDRESSED

- **Statistical robustness.** `cell_statistics` adds Wilson score intervals + two-proportion
  significance + `robustly_better` (A beats B only if A's lower bound > B's point AND the gap
  is significant) + `min_n_for_resolution`. CapabilityCell now reports
  `success_rate_ci_low/high`: a 3/3 cell shows **[0.44, 1.0]** not 1.0; a 200-sample cell a
  tight interval. The real live-bakeoff cells now carry honest CIs (openai 10/10 → [0.72,
  1.0]). Small-sample evidence is quantified, not assumed.

## Net

The live-evidence gaps (WS14, WS18, WS19, WS6) are closed or verified, the report warehouse
was already built, and the small-sample caveat is addressed with proper confidence intervals.
Remaining out-of-scope: local LoRA (no GPU) and a web operator UI.
