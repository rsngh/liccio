"""Full CLI lifecycle (round-1 two-day D2B7)."""

from __future__ import annotations

import json

import pytest
from git import Repo
from typer.testing import CliRunner

from acp.cli.main import app
from acp.core.config import reset_settings

runner = CliRunner()
FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("ACP_ARTIFACT_DIR", str(tmp_path / "art"))
    monkeypatch.setenv("ACP_WORKSPACE_DIR", str(tmp_path / "ws"))
    reset_settings()
    yield tmp_path
    reset_settings()


def _git_repo(tmp_path):
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
    return src


def test_agents_health(env) -> None:
    out = runner.invoke(app, ["agents", "list"])
    assert out.exit_code == 0
    assert "patch" in out.output and "fake" in out.output
    one = runner.invoke(app, ["agents", "health", "patch"])
    assert one.exit_code == 0
    assert "available" in one.output


def test_cli_full_lifecycle_and_run_graph(env, monkeypatch) -> None:
    src = _git_repo(env)
    # repo add (capture id)
    r = runner.invoke(app, ["repo", "add", str(src), "--name", "demo", "--branch", "master"])
    assert r.exit_code == 0
    repo_id = r.output.split()[1]
    # repo index
    assert runner.invoke(app, ["repo", "index", repo_id]).exit_code == 0
    # task create
    from acp.api.service import AppService

    svc = AppService()
    task = svc.create_task(repo_id, "Fix divide bug", "zero divisor",
                           metadata={"files": {"calculator.py": FIXED}})
    # run start
    rs = runner.invoke(app, ["run", "start", task.id])
    assert rs.exit_code == 0, rs.output
    run_id = json.loads(rs.output)["run_id"]
    # run graph after a fresh process (new AppService inside the command)
    g = runner.invoke(app, ["run", "graph", run_id, "--counts"])
    assert g.exit_code == 0
    counts = json.loads(g.output)
    assert counts["attempts"] >= 1
    assert counts["reward_events"] >= 1
    # full graph (default) carries the actual entities
    full = json.loads(runner.invoke(app, ["run", "graph", run_id]).output)
    assert isinstance(full["attempts"], list) and full["attempts"]
    # evidence + evaluation surfaces
    assert runner.invoke(app, ["run", "evidence", run_id]).exit_code == 0
    assert runner.invoke(app, ["run", "evaluation", run_id]).exit_code == 0


def test_cli_review_label_resumes_run(env) -> None:
    src = _git_repo(env)
    r = runner.invoke(app, ["repo", "add", str(src), "--name", "demo", "--branch", "master"])
    repo_id = r.output.split()[1]
    from acp.api.service import AppService

    svc = AppService()
    # high-risk task pauses for human review
    task = svc.create_task(repo_id, "Update auth password hashing", "auth",
                           metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)
    assert state.human_review_item_id
    out = runner.invoke(app, ["reviews", "label", state.human_review_item_id,
                              "--verdict", "pass", "--reason", "ok"])
    assert out.exit_code == 0
    assert "resumed" in out.output
