# Alpha 24 — Tier 1–3 / 15-Area Execution Tracker

North star: **a trusted operating system for coding-agent intelligence**. Every area ships
real modules + unit tests + at least one artifact (live where appropriate), gated green,
honoring the safety invariants (contaminated/inconclusive attempts never train; measured
gain required before deploy; poisoning blocked; staged-canary + rollback; secret-scanned
artifacts; timeouts are infra, not capability).

Substrate reused: `benchmark_suite` (execution-verified graded tasks), `vendor_native` +
`openai_harness`, `measurement_hygiene`/`measurement_quality`, `capability_matrix`,
`skill_canary_platform`, provenance/poisoning defense.

## P0 preflight — DONE (Alpha 22/23)
- [x] report truth + sync-status; artifact manifest source of truth
- [x] WS18 Docker live-security gate (9/9, production-gated)
- [x] WS19 `live_vendor` marker + `acp eval vendor-harness-live`

## Tier 1 — live orchestration
- [ ] 1. Layered advisor / metacognitive escalation
- [ ] 2. Weak-model best-of-k candidates + execution comparator
- [ ] 3. AutoTTS-style topology controller search
- [ ] 4. Meta-Harness / harness optimization
- [ ] 5. Synthetic task-corpus generator / active benchmark builder

## Tier 2 — context, memory, abstention, training data, deterministic boundaries
- [ ] 6. Context-strategy optimizer: grep vs embeddings vs hybrid
- [ ] 7. Memory lifecycle / aging benchmark
- [ ] 8. Stochastic–deterministic boundary (SDB) contracts
- [ ] 9. Selective abstention / sufficient-context gate
- [ ] 10. Workflow distillation / agentless training data

## Tier 3 — research frontier
- [ ] 11. HeavySkill / internalized parallel-deliberation skill
- [ ] 12. Tool-use RL / format-adherence training data
- [ ] 13. DGM-style open-ended variant archive
- [ ] 14. DeepConf / confidence-based trace pruning
- [ ] 15. Research-engineering benchmark hardening (NanoGPT-style)

## Release
- [ ] ALPHA24_REPORT.md + ALPHA24_CHECKLIST.md
- [ ] full gate green; all artifacts valid; push
