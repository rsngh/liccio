"""Policy decision dossier (Alpha 11, WS3)."""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.routing.bandit import SimulatedBanditPolicy


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'd.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("c", str(src), default_branch="master")


def test_dossier_explains_a_run(tmp_path) -> None:
    svc = AppService(_settings(tmp_path))
    svc.policy = SimulatedBanditPolicy(epsilon=0.2)
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": fixed}},
                          acceptance_criteria=["divide(x,0) raises"])
    state = svc.run_task(task.id)

    d = svc.policy_dossier(state.run_id)
    assert d["viability"] is not None
    assert d["viability"]["task_type"] == "bugfix"
    assert d["chosen_action"] is not None
    assert d["context_strategy"]
    assert isinstance(d["why_chosen"], list) and d["why_chosen"]
    # candidate scores -> why-not explanations for non-chosen candidates
    assert isinstance(d["why_not_others"], dict)
    assert "risk_level" in d
