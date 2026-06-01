"""Adaptive routing wired into the live workflow (round-1 goal §3, §4)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'r.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "d"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("d", str(src), default_branch="master")


def test_routing_decision_has_multiple_candidates(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    task = service.create_task(repo.id, "Fix divide", "zero",
                              metadata={"files": {"calculator.py": FIXED}})
    service.run_task(task.id)
    decision = service._runners[list(service._runs)[0]].artifacts.routing_decision
    # bandit decision over patch + fake -> >1 candidate, real propensity, scores logged
    assert len(decision.candidate_actions) >= 2
    assert 0.0 < decision.action_probability <= 1.0
    assert decision.policy_version.startswith("bandit")


def test_policy_learns_across_runs(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    for _ in range(6):
        task = service.create_task(repo.id, "Fix divide bug", "zero divisor",
                                  metadata={"files": {"calculator.py": FIXED}})
        service.run_task(task.id)
    # the shared bandit policy accumulated per-context arm stats
    assert service.policy.arms
    ctx_arms = next(iter(service.policy.arms.values()))
    assert any(stat.n > 0 for stat in ctx_arms.values())
