"""Control-plane health snapshot (Alpha 9)."""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'h.db'}",
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


def test_health_snapshot_unifies_state(tmp_path) -> None:
    svc = AppService(_settings(tmp_path))
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    for i in range(3):
        t = svc.create_task(repo.id, f"Fix divide {i}", "zero divisor",
                            metadata={"files": {"calculator.py": fixed}},
                            acceptance_criteria=["raises"])
        svc.run_task(t.id)

    health = svc.control_plane_health()
    assert health["counts"]["tasks"] >= 3
    assert health["counts"]["viability_assessments"] >= 3
    assert "ope" in health and "log_size" in health["ope"]
    assert "readiness" in health
    assert isinstance(health["readiness"]["has_viability_provenance"], bool)
    assert health["readiness"]["has_viability_provenance"] is True
