"""Persisted eval reports (round-2 Block F)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from acp.api.app import create_app
from acp.api.service import AppService
from acp.core.config import ACPSettings


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'e.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def test_context_benchmark_persisted(service) -> None:
    run = service.run_context_benchmark(files=30)
    assert run.kind == "context_benchmark"
    assert run.summary["recall_at_10"] >= 0.0
    # durable: a fresh service reads it back
    fresh = AppService(service.settings)
    got = fresh.get_eval_run(run.id)
    assert got is not None and got["kind"] == "context_benchmark"
    report = fresh.get_eval_report(run.id)
    assert report and "recall_at_5" in report["content"]


def test_bakeoff_persisted_with_cases(service) -> None:
    run = service.run_bakeoff_eval(seeds=1)
    assert run.kind == "bakeoff"
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.schemas.eval import EvalCase

    with session_scope(service.sessions) as s:
        cases = EntityStore(s).list_by(EvalCase, eval_run_id=run.id)
    assert cases  # per-cell rows persisted


def test_eval_api_endpoints(service) -> None:
    client = TestClient(create_app(service))
    posted = client.post("/evals/context-benchmark?files=20").json()
    rid = posted["id"]
    assert client.get("/evals/runs").status_code == 200
    assert client.get(f"/evals/runs/{rid}").json()["kind"] == "context_benchmark"
    assert "content" in client.get(f"/evals/runs/{rid}/report").json()
    assert client.get("/evals/runs/nope").status_code == 404
