"""Post-merge outcome replay -> matured rewards -> policy update (round-3 R3-7)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.db.repositories import EntityStore
from acp.db.session import session_scope
from acp.schemas.learning import RewardEvent

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'pm.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def _run(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "pm"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = svc.create_repo("pm", str(src), default_branch="master")
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})
    return svc.run_task(task.id)


def test_replay_matures_reward_and_updates_policy(service, tmp_path) -> None:
    state = _run(service, tmp_path)
    # record a revert outcome for the selected attempt
    service.ingest_outcome(state.task_id, state.selected_attempt_id, reverted=True)

    before = service.policy.export_arms()
    result = service.replay_post_merge_outcomes()
    assert result["replayed"] >= 1
    assert result["reverted"] >= 1
    assert result["arms_updated"] >= 1
    assert "drift" in result

    # matured (post_merge) reward events exist
    with session_scope(service.sessions) as s:
        rewards = EntityStore(s).list_by(RewardEvent)
    assert any(r.label_source == "post_merge" and r.matured_at for r in rewards)
    # the policy arms changed (a revert pushed the arm's success proxy down)
    assert service.policy.export_arms() != before
