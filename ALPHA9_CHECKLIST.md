# Alpha 9 — multi-objective, continuously-monitored decision system: checklist

Alpha 9 turns the learned-governance platform (Alpha 8) into a **multi-objective,
continuously monitored decision system**: Pareto routing, drift→demote, preference
learning, per-decision counterfactual regret, an active-learning loop, a
continuous-learning scheduler, and a unified control-plane health snapshot.

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| 1 | This checklist + `ALPHA9_REPORT.md` + 5 artifacts + `make alpha9-artifacts`. |
| 2/3/4 | **Pareto routing policy** (`routing/pareto_policy.py`): `ParetoRoutingPolicy` (RoutingPolicy) + 6 weight **profiles** (cost_saver/balanced/success_max/risk_min/latency_min/human_review_min) with hard constraints; same candidates → different rational choices; `profile_target` gives an OPE target per profile. |
| 5 | **Drift detection + auto-demote** (`learning/drift.py`): accuracy-drop + PSI + recent high-risk-FN → demotes a promoted learned model back to advisory. |
| 6 | **Preference learning** (`learning/preference.py`): pairwise Bradley-Terry model from human labels (learned reward signal). |
| 7 | **Counterfactual what-if** (`routing/counterfactual.py`): per-decision regret vs the best alternative + log-wide `total_regret`. |
| 8 | **Control-plane health** (`AppService.control_plane_health`, `acp health`): status/degraded + counts + OPE readiness + learned-model promotions + Pareto profiles + artifact freshness. |
| 9 | **Active-learning exploration executor** (`learning/exploration_executor.py`): turns coverage gaps into budget/risk-bounded probes; simulated exploration raises sufficient-cell coverage. |
| 10 | **Continuous-learning scheduler** (`learning/scheduler.py`): ordered, idempotent, resumable, fault-tolerant job batch. |

## Required artifacts (committed, manifest-validated)

- `evals/reports/pareto_routing.json` — profile choices over a shared candidate set.
- `evals/reports/drift_demote.json` — drift detected → model demoted to advisory.
- `evals/reports/preference_learning.json` — pairwise preference model eval.
- `evals/reports/counterfactual_regret.json` — log-wide regret + a what-if.
- `evals/reports/control_plane_health.json` — health snapshot.

## Gate

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src
uv run alembic upgrade head
make alpha9-artifacts && acp reports validate
```
