"""Routing policy first-class in the live loop (round-1 two-day D2B1 / §F)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'rf.db'}",
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
        '[project]\nname = "rf"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("rf", str(src), default_branch="master")


def _runs(svc, repo, k):
    for _ in range(k):
        t = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                            metadata={"files": {"calculator.py": FIXED}})
        svc.run_task(t.id)


def test_live_decision_multiple_candidates_and_feature_hash(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    _runs(service, repo, 1)
    dec = service._runners[next(iter(service._runs))].artifacts.routing_decision
    assert len(dec.candidate_actions) >= 2
    assert dec.feature_hash
    assert dec.model_scores  # candidate scores persisted


def test_policy_arms_update_and_snapshot(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    _runs(service, repo, 8)  # some runs may explore -> pause; most produce reward
    assert service.policy.arms
    snap = service.train_policy()
    assert snap.params["arms"]
    assert snap.metadata["metrics"]["reward_events"] >= 4


def test_off_policy_report(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    _runs(service, repo, 8)
    report = service.off_policy_report()
    assert report["n_decisions_with_reward"] >= 4
    assert report["propensity_coverage"] > 0
    assert report["mean_reward_by_action"]


def test_promote_rollback_affect_selection(service) -> None:
    a = service.train_policy()
    b = service.train_policy()
    service.promote_policy(b.id)
    reg = service._registry()
    assert reg.champion().id == b.id
    service.rollback_policy(a.id)
    assert service._registry().champion().id == a.id
