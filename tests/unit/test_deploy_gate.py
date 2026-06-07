"""Production-ish deploy gate tests (GOALS Alpha 44 P8)."""

from __future__ import annotations

from acp.deploy.worker_queue import production_health_gate, run_jobs


def test_100_concurrent_jobs_complete_with_unique_run_ids() -> None:
    run = run_jobs(100, n_workers=8)
    gate = production_health_gate(run, 100)
    assert gate["checks"]["all_jobs_completed"]
    assert gate["checks"]["no_duplicate_run_ids"]
    assert gate["checks"]["no_orphan_workspaces"]
    assert gate["production_ready"]
    assert gate["n_jobs"] == 100


def test_stale_deployment_fails_gate() -> None:
    run = run_jobs(20, n_workers=4)
    gate = production_health_gate(run, 20, deployment_fresh=False)
    assert not gate["production_ready"]
    assert not gate["checks"]["deployment_fresh"]


def test_unique_run_ids_under_concurrency() -> None:
    run = run_jobs(200, n_workers=16)
    assert len(set(run.run_ids)) == 200
    assert run.orphan_workspaces == []


def test_handler_failure_flagged() -> None:
    run = run_jobs(10, n_workers=2, handler=lambda job: job.payload["i"] != 3)
    gate = production_health_gate(run, 10)
    assert not gate["checks"]["all_jobs_ok"]   # one job failed -> flagged, not hidden
