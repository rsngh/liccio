"""Full run-graph reconstruction (round-1 two-day D1B2 / §A)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'g.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )


def _run(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "g"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = svc.create_repo("g", str(src), default_branch="master")
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})
    return svc.run_task(task.id)


def test_full_run_graph_contains_expected_entities(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    graph = svc.full_run_graph(state.run_id)
    assert graph["task"]
    assert graph["snapshot"]
    assert graph["context_pack"]
    assert graph["verification_plan"]
    assert graph["routing_decision"]
    assert graph["attempts"]
    assert graph["verification_runs"]
    assert graph["evidence"]
    assert graph["evaluation"]
    assert graph["weak_labels"]
    assert graph["reward_events"]
    assert graph["spans"]


def test_run_graph_survives_service_restart(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    # fresh service (new process) reconstructs without _runs/_runners
    fresh = AppService(settings)
    assert not fresh._runs
    graph = fresh.full_run_graph(state.run_id)
    assert graph["state"]["run_id"] == state.run_id
    assert graph["attempts"]
    assert graph["reward_events"]


def test_every_id_in_workflow_state_resolves(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    graph = AppService(settings).full_run_graph(state.run_id)
    if state.snapshot_id:
        assert graph["snapshot"] is not None
    if state.context_pack_id:
        assert graph["context_pack"] is not None
    if state.routing_decision_id:
        assert graph["routing_decision"] is not None
    if state.evaluation_result_id:
        assert graph["evaluation"] is not None
