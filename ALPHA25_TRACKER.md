# Alpha 25+ — Production Coherence, Evidence Truth & Compute Policy (Round 24)

Driven by the round-24 review: fix report drift, make infra flakes first-class measurement
data, escape the easy-task ceiling, and turn expensive compute into a ledger-gated policy.

## Alpha 25 — production coherence & evidence truth
- [x] ReleaseTruthManifest + `acp reports sync-status --strict` (report-truth HARD gate)
- [x] Fixed stale CURRENT_STATUS header (Round 12 -> Alpha 25; 258->279 src; 46->84 artifacts)
- [x] sync-status now syncs source + artifact counts (not just tests)
- [x] Infra-flake taxonomy: every infra event -> infra/inconclusive, never model/skill failure
- [x] `report_truth_consistent` production gate (stale status fails closed)
- [x] docker-security-live: mid-run daemon loss -> clean skip (prior commit)
- [x] Tests A (report truth), B (infra classification), H (production fail-closed)

## Test F — escape the easy-task ceiling (evidence depth)
- [x] Hard greedy-trap cohort (coin_change/word_break/lis/max_product/min_path_sum), proven offline
- [x] LIVE: single-shot reliability 0.84 (NOT ceiling); best-of-8 -> 1.0, lift +0.16

## Alpha 29 — compute-escalation policy
- [x] compute_policy: choose arm by reliability + risk/value; ComputeSpendLedger marginal value
- [x] Escalate to expensive arms only where marginal value positive
- [x] LIVE compute-policy bakeoff: policy withholds escalation when single-shot suffices (variance-honest)

## Release
- [ ] ALPHA25_REPORT.md + checklist; full gate; push

## Alpha 26 — vendor corpus (vendor proof depth)
- [x] run_vendor_corpus_live: claude_code over full graded+hard corpus -> capability matrix
- [x] LIVE: baseline 0.909; full-suite-discipline skill causes -0.636 NEGATIVE TRANSFER
      (helped weak model in A23, hurts strong vendor harness) -> governance blocks deploy

## Alpha 28 — skill-library hardening
- [x] skill_staleness: keep/revalidate/narrow_scope/retire from age/uses/recent-lift

## Measurement-trust correction (Alpha 26)
- [x] Vendor "negative transfer" exposed as activation/infra failure (claude_code degraded)
- [x] run_vendor_corpus_live activation-aware + test_vendor_activation
- [x] benchmark_runner activation-aware (activation_rate + activated_solve_rate) — generalized

## Alpha 32 seed — evidence-gap analyzer
- [x] evidence_gap: prioritized gaps + experiment plan; `acp evidence-gaps` CLI
