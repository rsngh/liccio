"""Soak metrics + concurrency isolation (round-1 two-day D2B5 / §H)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.evaluation.soak import run_concurrent_soak, run_soak, soak_to_markdown

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 's.db'}",
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
        '[project]\nname = "s"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("s", str(src), default_branch="master")


def test_soak_report_schema(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    rep = run_soak(service, repo.id, iterations=8, task_mix=["bugfix", "fail"])
    for key in ("iterations", "status_distribution", "rss_kb_start", "rss_kb_end",
                "memory_growth_ratio", "open_fds", "worktree_dirs", "artifact_bytes",
                "latency_p50", "latency_p95", "policy_arm_contexts", "thresholds"):
        assert key in rep
    assert "Soak report" in soak_to_markdown(rep)


def test_concurrent_workflows_isolated(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    rep = run_soak(service, repo.id, iterations=12, task_mix=["bugfix"])
    # every run got a unique id + isolated workspace; no DB corruption
    assert rep["unique_run_ids"] == 12
    assert rep["thresholds"]["all_runs_unique"]
    assert rep["unique_workspaces"] >= 12


def test_no_orphan_worktrees_after_soak(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    rep = run_soak(service, repo.id, iterations=10, task_mix=["bugfix"])
    assert rep["thresholds"]["no_unbounded_worktrees"]
    assert rep["thresholds"]["memory_growth_ok"]


def test_true_concurrent_soak_no_corruption(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    rep = run_concurrent_soak(service.settings, repo.id, iterations=12, concurrency=4,
                              task_mix=["bugfix"])
    assert rep["concurrency"] == 4
    assert rep["duplicate_run_ids"] == 0
    assert rep["db_lock_errors"] == 0
    assert rep["thresholds"]["no_db_corruption"]
    assert rep["thresholds"]["all_runs_unique"]
    assert rep["unique_run_ids"] == 12
    assert rep["latency_p95"] >= rep["latency_p50"]
