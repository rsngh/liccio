"""Persisted routing policy alpha (round-2 Block J)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'p.db'}",
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
        '[project]\nname = "p"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("p", str(src), default_branch="master")


def test_policy_state_survives_restart(settings, tmp_path) -> None:
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    for _ in range(5):
        t = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                            metadata={"files": {"calculator.py": FIXED}})
        svc.run_task(t.id)
    assert svc.policy.arms
    # fresh process loads the persisted arms
    fresh = AppService(settings)
    assert fresh.policy.arms
    assert fresh.policy.export_arms() == svc.policy.export_arms()


def test_observe_reward_updates_persisted_arm(settings, tmp_path) -> None:
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    t = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                        metadata={"files": {"calculator.py": FIXED}})
    svc.run_task(t.id)
    arms = svc.policy.export_arms()
    assert any(stat["n"] > 0 for ctx in arms.values() for stat in ctx.values())


def test_policy_selects_best_arm_after_training() -> None:
    # deterministic exploit policy; train arm B to dominate, then it is chosen
    pol = SimulatedBanditPolicy(seed=1, epsilon=0.0)
    cands = [RoutingAction(agent_kind="fake", agent_name="A"),
             RoutingAction(agent_kind="fake", agent_name="B")]
    feats = {"task_type": "bugfix", "risk_level": "medium"}
    for _ in range(20):
        dec = PolicyDecision(policy_version="v", action=cands[1], action_probability=0.5,
                             context_key="bugfix|medium")
        pol.observe_reward(dec, RewardEvent(task_id="t", reward=5.0, components={"x": 5.0}))
    chosen = pol.choose_action(feats, cands)
    assert chosen.action.agent_name == "B"


def test_drift_detector_flags_reward_drop(settings) -> None:
    svc = AppService(settings)
    # synthetic reward history: high baseline then a drop
    for i in range(10):
        svc._save(RewardEvent(task_id=f"t{i}", reward=5.0, components={"x": 5.0}))
    for i in range(10):
        svc._save(RewardEvent(task_id=f"d{i}", reward=0.1, components={"x": 0.1}))
    report = svc.drift_report(window=10)
    assert report["drift_detected"] is True
    assert report["drop"] > 0
    # persisted as an eval run
    assert any(r["kind"] == "drift" for r in svc.list_eval_runs())
