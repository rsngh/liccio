# Alpha 11 — production-readiness candidate: checklist

Alpha 11 turns the manifest-validated lab into a **production-readiness candidate**:
live routing objectives, a per-run decision dossier, mode-gated health, durable
drift demotion, governed preference reward, a data-governance red-team, larger
corpus + realistic fixtures, and a production policy pack.

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| 1 | Fresh release hygiene: `reports/pytest.txt` + `coverage.txt`, docs-consistency. |
| 2 | **Pareto live config** (`core/pareto_config.py`): task_type→profile map + high-risk safety override + validation. |
| 3 | **Policy decision dossier** (`core/policy_dossier.py`, `acp policy dossier`): why this agent/context/cost/risk + why-not others, from the run graph. |
| 4 | **Health release modes** (`acp health --mode lab|staging|production`): production gates (docker-live, OPE overlap, fresh tests, manifest); nonzero exit when unready. |
| 5 | **Docker live-security campaign** (`docker_security_live` + gate) — env-gated. |
| 6 | **Vendor harness live** (`vendor_harness_live.json`) — capability/availability reported; live runs env-gated. |
| 7 | **Preference reward governance** (`learning/reviewer_reliability.py`): reviewer reliability + gated combined reward (advisory until thresholds pass). |
| 8 | **Durable drift/demotion persistence** (`schemas/drift.py` + migration + `run_and_persist_drift`): reports/demotion-events/promotion-state are queryable. |
| 9 | **Active-learning executor** (`learning/exploration_run.py`): budget/risk-bounded probes raise coverage + OPE overlap. |
| 10 | **Scheduler productionization** (`learning/scheduler_prod.py`): dependency graph + single-writer lock + retry + stale-flagging. |
| 11 | **Data-governance red-team** (`evaluation/data_governance_redteam.py`): 6 attacks all blocked/flagged, zero leaks. |
| 12 | **Mixed empirical corpus** (`evaluation/mixed_corpus.py`). |
| 13 | **Realistic repo fixtures** (`evaluation/repo_fixtures.py`): 8 kinds. |
| 19 | **Production policy pack** (`core/policy_pack.py`): lab/staging/production policies + enforce(). |
| 20 | This checklist + `ALPHA11_REPORT.md` + `make alpha11-artifacts` + docs-consistency; 34 manifest-validated artifacts. |

## Required artifacts (committed, manifest-validated)

- `evals/reports/policy_dossier.json`
- `evals/reports/preference_reward_gate.json`
- `evals/reports/data_governance_redteam.json`
- `evals/reports/drift_persistence.json`
- `evals/reports/exploration_executor.json`
- `evals/reports/scheduler_report.json`
- `evals/reports/mixed_empirical_corpus.json`
- `evals/reports/control_plane_health_production.json`
- `evals/reports/vendor_harness_live.json`
- `evals/reports/local_lora_pilot.json`

## Gate

```bash
uv run pytest -q --timeout=300 && uv run ruff check . && uv run mypy src
uv run alembic upgrade head
make alpha9-artifacts && make alpha10-artifacts && make alpha11-artifacts
acp reports validate && acp health --mode lab
```
