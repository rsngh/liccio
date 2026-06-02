# Alpha 9 plan — autonomous, continuously self-optimizing control plane

Alpha 8 made governance *learned* (viability/strategy/trust/repair models from
exhaust) and *explainable* (decision cards, self-improvement loop). Alpha 9 makes
the control plane **autonomous and continuously self-optimizing**, with the safety
rails to do so responsibly.

## Mission

> ACP should route on the full (success, cost, latency, risk) frontier, detect
> when its learned models drift from live outcomes and demote them automatically,
> answer counterfactual "what if we'd routed differently" questions, and expose a
> single control-plane health snapshot — all gated by the Alpha-7/8 promotion and
> safety machinery.

## Workstreams

1. **Multi-objective Pareto routing** (`routing/pareto.py`) — select non-dominated
   actions over (success↑, cost↓, latency↓, risk↓); scalarization with weights;
   explain the frontier.
2. **Drift detection + auto-demote** (`learning/drift.py`) — compare a learned
   model's predictions to realized outcomes over a window; flag accuracy drop /
   distribution shift; demote a promoted model back to advisory on drift.
3. **Counterfactual what-if simulator** (`routing/counterfactual.py`) — given a
   logged decision + the fitted reward model, estimate the outcome of alternative
   actions (the inverse of OPE: per-decision, not per-policy).
4. **Control-plane health snapshot** (`AppService.control_plane_health`) — unify
   viability stats, capability-matrix coverage, policy promotion status,
   calibration, and budget into one status object + CLI.
5. **Preference/reward learning** (`learning/preference.py`) — a pairwise
   preference model over human labels feeding a learned reward signal.

## Gate

`uv run pytest -q && uv run ruff check . && uv run mypy src` stays green; each
workstream ships focused tests; nothing auto-promotes without the existing gates.
