"""Closed-loop self-improvement capstone (Alpha 8)."""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'si.db'}",
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


def test_self_improvement_cycle_runs_from_exhaust(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    # Generate exhaust: several solved bugfix runs.
    for i in range(5):
        t = svc.create_task(repo.id, f"Fix divide {i}", "zero divisor",
                            metadata={"files": {"calculator.py": fixed}},
                            acceptance_criteria=["divide(x,0) raises"])
        svc.run_task(t.id)

    report = svc.self_improvement_report()
    assert "datasets" in report and "viability" in report
    assert report["datasets"]["viability"] >= 1
    # The cycle reaches a promotion decision (advisory-or-promote) per model.
    assert "promotions" in report
    # It never crashes and always explains itself.
    assert isinstance(report["notes"], list)
