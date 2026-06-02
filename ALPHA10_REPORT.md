# Alpha 10 report — scale & production-lab hardening

Alpha 10 moves from "the mechanisms exist" to "they hold at scale and the
production path is hardened." It generates a large empirical corpus, benchmarks
storage/performance for sub-quadratic behavior, expands the security/prompt-
injection suite, and adds model/data governance.

## Headline results (committed, manifest-validated)

- **Large empirical corpus** (`large_empirical_corpus.json`): 930 sufficiently-
  sampled capability cells (>500 target) and 1,740 preference pairs (>1,000
  target), with Pareto frontier sizes per task group and an OPE-overlap estimate.
- **Scale is sub-quadratic** (`storage_scale_v2.json`): per-N latency for run-graph
  listing, capability-matrix build, OPE build, dataset build, artifact validation,
  and health aggregation grows sub-quadratically across the sweep.
- **Security v2 holds** (`security_injection_v2.json`): 10 attack classes —
  including supply-chain mutation and training-data / reward-model poisoning — are
  every one escalated or flagged, with zero planted-secret leakage.
- **Governance enforced**: no private-repo data enters the global training pool
  without an explicit allowlist; repo-local training is permitted; model rollback
  plans are recorded.

## Gated / deferred (environment-bound)

- Docker live-security gate, vendor-harness live campaign, and local LoRA training
  require Docker / vendor keys / a GPU and skip cleanly here; the code paths +
  gates exist (`docker_security_live`, vendor contract tests, `local_lora`).
- The learned-viability canary promotion campaign reuses the Alpha-8 promotion +
  Alpha-9 drift machinery; it activates once live high-risk outcomes accrue.
