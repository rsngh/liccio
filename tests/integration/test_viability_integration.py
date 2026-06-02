"""Viability assessment is produced, persisted, and surfaced (Alpha 7, WS1)."""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'v.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("c", str(src), default_branch="master")


def test_viability_persisted_and_in_run_graph(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    task = svc.create_task(repo.id, "Fix divide bug", "divide() returns 0 on zero divisor",
                          metadata={"files": {"calculator.py": fixed}},
                          acceptance_criteria=["divide(x,0) raises ZeroDivisionError"])
    state = svc.run_task(task.id)

    graph = svc.full_run_graph(state.run_id)
    v = graph["viability"]
    assert v is not None
    assert v["task_id"] == task.id
    assert v["task_type"] == "bugfix"
    assert "viable_context_strategies" in v
    # The routed context strategy must be one viability allowed.
    decision = graph["routing_decision"]
    if decision is not None:
        assert decision["action"]["context_strategy"] in v["viable_context_strategies"] \
            or decision["action"]["context_strategy"] == "minimal"
