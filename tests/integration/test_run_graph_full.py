"""Full RunGraph schema + secret-safety (round-2 Block B)."""

from __future__ import annotations

import json
import os

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.schemas.graph import RunGraph

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


def test_full_run_graph_schema(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    graph = svc.full_run_graph(state.run_id)
    model = RunGraph.model_validate(graph)  # validates the full shape
    assert model.state["run_id"] == state.run_id
    assert model.attempts and model.reward_events
    assert model.evaluation is not None


def test_run_graph_after_restart(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    fresh = AppService(settings)
    assert not fresh._runs
    model = RunGraph.model_validate(fresh.full_run_graph(state.run_id))
    assert model.attempts and model.spans and model.reward_events


def test_all_workflow_state_ids_resolve(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    graph = RunGraph.model_validate(svc.full_run_graph(state.run_id))
    ids = graph.referenced_ids()
    for sid in (state.snapshot_id, state.context_pack_id, state.routing_decision_id,
                state.evaluation_result_id, state.reward_event_id):
        if sid:
            assert sid in ids, f"{sid} missing from graph"


def test_artifact_refs_resolve(settings, tmp_path) -> None:
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    graph = svc.full_run_graph(state.run_id)
    # any command-run artifact refs must resolve in the artifact store
    for cmd in graph["command_runs"]:
        for ref_uri in (cmd.get("stdout_artifact_ref"), cmd.get("stderr_artifact_ref")):
            if ref_uri:
                from acp.schemas.trace import ArtifactRef

                data = svc.artifact_store.get_bytes(ArtifactRef(uri=ref_uri))
                assert isinstance(data, bytes)


def test_no_raw_secret_in_run_graph(settings, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ACP_OPENAI_API_KEY", "sk-super-secret-graph-000")
    from acp.core.config import reset_settings

    reset_settings()
    svc = AppService(settings)
    state = _run(svc, tmp_path)
    blob = json.dumps(svc.full_run_graph(state.run_id))
    assert "sk-super-secret-graph-000" not in blob
    os.environ.pop("ACP_OPENAI_API_KEY", None)
