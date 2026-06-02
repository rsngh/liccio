# Alpha 9 report — multi-objective, continuously-monitored decision system

Alpha 8 made ACP learn from its own exhaust. Alpha 9 makes the routing *decision
itself* multi-objective and continuously monitored: it reasons over Pareto
trade-offs, detects when learned models drift and auto-demotes them, learns
pairwise preferences from human labels, computes per-decision counterfactual
regret, runs an active-learning loop to fill coverage gaps, and exposes one
control-plane health snapshot. See `ALPHA9_CHECKLIST.md`; plan in `GOALS.md`.

## Headline results (committed, manifest-validated)

- **Pareto routing is profile-driven** (`pareto_routing.json`): on one shared
  candidate set, `cost_saver` picks the cheap adapter while `success_max` picks
  the harness — different rational choices from the same frontier.
- **Drift demotes unsafe models** (`drift_demote.json`): a window where confident
  predictions stop matching realized outcomes is detected (accuracy drop + PSI +
  recent high-risk false negatives) and the promoted learned model is
  auto-demoted back to advisory.
- **Preferences are learnable** (`preference_learning.json`): a pairwise model
  fit from human labels scores attempts as a learned reward.
- **Counterfactual regret is computed per decision** (`counterfactual_regret.json`):
  the log-wide regret of the behavior policy vs always picking the best arm, plus
  a per-decision what-if.
- **One health snapshot** (`control_plane_health.json`, `acp health`): status /
  degraded, entity counts, OPE readiness, learned-model promotions, Pareto
  profiles, and artifact freshness — degraded when a critical gate is stale.
- **Active learning + scheduling**: the exploration executor turns capability-
  matrix gaps into budget/risk-bounded probes (simulated coverage +54 cells), and
  the continuous-learning scheduler runs the pipeline idempotently and
  fault-tolerantly.

## Honest limitations

- Artifacts use synthetic/deterministic data so they are reproducible; the
  Pareto/drift/preference machinery is real but its *inputs* become rich only with
  the Alpha-10 large-corpus + live campaigns.
- Pareto routing is wired as a `RoutingPolicy` and OPE target; making it the live
  default is gated behind the OPE promotion gate (Alpha 7) per profile.
- Drift auto-demote is duck-typed onto the ensemble flag; the persisted
  drift/demotion entities + nightly scheduler hook are scoped for Alpha 10.
