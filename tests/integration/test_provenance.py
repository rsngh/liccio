"""Provenance / persistence completeness (round-1 goal §A.1, §A.2)."""

from __future__ import annotations

import pytest

from acp import schemas as s
from acp.api.service import AppService
from acp.cli.demos import run_bugfix_demo
from acp.core.config import ACPSettings
from acp.db.repositories import EntityStore
from acp.db.session import session_scope


@pytest.fixture
def service(tmp_path) -> AppService:
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'prov.db'}",
        artifact_dir=tmp_path / "art",
        workspace_dir=tmp_path / "ws",
    )
    return AppService(settings)


def test_full_persistent_graph(service) -> None:
    result = run_bugfix_demo(service, service.settings.workspace_dir)
    task_id = result["task_id"]

    # A fresh store (simulating a new process) reconstructs the run from the DB.
    fresh = AppService(service.settings)
    with session_scope(fresh.sessions) as session:
        es = EntityStore(session)
        assert es.get(s.Task, task_id) is not None
        assert es.get(s.RepoSnapshot, result["snapshot_id"]) is not None
        assert es.get(s.ContextPack, result["context_pack_id"]) is not None
        assert es.get(s.RoutingDecision, result["routing_decision_id"]) is not None
        assert es.get(s.EvaluationResult, result["evaluation_result_id"]) is not None
        assert es.get(s.RewardEvent, result["reward_event_id"]) is not None

        by_task = es.all_for_task(task_id)
        assert "AgentAttempt" in by_task
        assert "VerificationPlan" in by_task
        assert "VerificationRun" in by_task
        assert "Evidence" in by_task
        assert "RewardEvent" in by_task
