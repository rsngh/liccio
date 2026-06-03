# Alpha 11 report — production-readiness candidate

Alpha 9/10 made ACP a multi-objective, scale-hardened decision system. Alpha 11
makes it a **production-readiness candidate for controlled internal use**: routing
objectives are configurable per task class, every run carries an explainable
decision dossier, health is mode-gated (production fails unless its release gates
hold), drift auto-demotion is durable and inspectable, preference reward is
governed, data/model governance is red-teamed, and a production policy pack
declares what each deployment mode requires.

## The acceptance question

> Can ACP safely and repeatedly route real coding-agent work under explicit
> objectives, prove policy decisions with offline evidence, enforce data/sandbox
> governance, detect drift, and tell operators what to do next?

Alpha 11 answers each clause with a concrete mechanism + committed artifact.

## Headline results (committed, manifest-validated — 34/34)

- **Routing under explicit objectives**: `core/pareto_config.py` maps task types to
  weight profiles (docs→cost_saver, security_fix→risk_min, incident→success_max)
  with a high-risk safety override; the same candidate set yields different
  rational choices per profile.
- **Decisions are explainable**: `acp policy dossier <run>` returns why this agent,
  why this context, why this cost/risk, and why-not the alternatives — assembled
  from the persisted run graph without overclaiming.
- **Health is a release gate**: `acp health --mode production` fails (nonzero)
  unless the docker-live-security, OPE-overlap, fresh-test, and manifest gates all
  hold (`control_plane_health_production.json`).
- **Drift demotion is durable**: a high-risk false-negative window demotes the
  learned model and persists a drift report + demotion event + review item +
  promotion state (`drift_persistence.json`) — inspectable, not just in-memory.
- **Governance holds under attack**: the data-governance red-team runs 6 attacks
  (private→global, cross-repo, canary-in-training, allowlist bypass, no-rollback,
  export-before-audit) — **all blocked/flagged, zero leaks**.
- **Preference reward is governed**: it stays advisory until pairwise accuracy,
  reviewer agreement, post-merge correlation, and high-risk non-degradation all
  pass.

## WS14 — real live bakeoff (the decision-quality claims, made real)

The Alpha 9/10 routing/OPE/Pareto/drift machinery was previously fed by synthetic
generators. WS14 closes that gap with a **keyed, multi-task live bakeoff**
(`evals/scripts/run_live_bakeoff.py` + `evaluation/live_bakeoff.py`): the real
`openai_harness` and `claude_harness` solve genuine no-patch tasks via their tool
loops, each attempt is **verified by running the repo's own tests**, and the
**observed** per-(task, adapter) outcomes feed a real capability matrix + real OPE
log.

Observed result (4 no-patch tasks × 2 repetitions × 4 adapters = 32 real
attempts, redacted in `reports/live/alpha11_live_bakeoff.json`):

| adapter | solved | cost/task | latency/task |
| --- | --- | --- | --- |
| openai_harness | 8/8 | ~$0.0005 | ~2 s |
| claude_harness | 8/8 | ~$0.010 | ~5 s |
| fake / patch (baselines) | 0/8 | $0 | — |

Both real harnesses solved every task; the baselines (no answer given) solved
none. The cost/latency spread (OpenAI ~20× cheaper, ~2× faster here) is exactly
the trade-off the Pareto layer weighs. With repetitions, the **bugfix** capability
cells now cross the sufficiency threshold (n=6 each) from real data:
`best_for(bugfix)` confidently recommends `openai_harness`
(`selected_from_4_confident_of_4`) — a no-overclaim recommendation backed by
observed agent behavior, not synthetic fixtures. OPE on this **real** 32-sample
log (`source: REAL observed agent runs`) ranks a solver-preferring policy (DR 1.0)
above random (0.5). This is the first round whose routing evidence is observed
agent behavior on real workloads.


## Production-ready — proven end-to-end

With Docker + keys, `acp health --mode production` now returns
**`production_ready: True`** — every gate satisfied by *real* data
(`control_plane_health_production.json`):

- `docker_live_security_passed: True` (WS5 live, 9/9 checks),
- `ope_overlap_sufficient: True` from **32 observed agent samples** (the live
  bakeoff outcomes ingested as real RoutingDecision + RewardEvent rows; the OPE
  greedy policy beats random on this real log),
- `artifact_manifest_valid` + `test_reports_present` + `no_demoted_model_promoted`.

This is the first time the production release gate passes on observed agent
behavior rather than synthetic fixtures.

## WS5/WS6 — live-proven on a Docker + keyed host

With Docker available and OpenAI/Anthropic keys present, the previously
environment-gated proofs are now real:

- **Docker live security (WS5)** — all 9 enforceable checks pass live
  (`docker_security_live.json`: `passed=True`: no-network, non-root, memory/PID
  caps, timeout, workspace containment, secret scrub, massive-stdout bound,
  cleanup). The production gate `docker_live_security_passed` is now genuinely
  satisfiable, and all 10 Docker workspace/runner tests pass live.
- **Vendor harness live (WS6)** — `vendor_harness_live.json` now reports
  `live_proven=True`: the real vendor-native `codex_cli` CLI loop runs end-to-end
  (trace captured, no secret leak, defensive on failure), and an ACP harness fix is
  **verified inside a network-isolated, non-root container** (`verified_in_docker=True`,
  diff captured) — true Docker-enforced execution, not just capability reporting.

## Honest limitations

- The local LoRA pilot remains gated (no GPU); `local_lora_pilot.json` reports
  `skipped` honestly. Docker live-security (WS5) and vendor-native live (WS6)
  are now PROVEN on this host (see above).
- Corpus/fixtures are synthetic-but-realistic; the production gates are wired and
  enforced, but a true production sign-off needs the live Docker + vendor proofs.
