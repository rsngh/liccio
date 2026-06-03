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

## Honest limitations

- Docker live-security, vendor-native live runs, and the local LoRA pilot are
  environment-gated (no Docker / vendor keys / GPU here); their artifacts report
  availability honestly (`vendor_harness_live.json`, `local_lora_pilot.json`).
- Corpus/fixtures are synthetic-but-realistic; the production gates are wired and
  enforced, but a true production sign-off needs the live Docker + vendor proofs.
