"""Docker workspace v1 (round-1 two-day D1B5).

Tests requiring a live Docker daemon are skipped when it is unavailable; the
argv-builder and factory fallback are tested unconditionally.
"""

from __future__ import annotations

import pytest
from git import Repo

from acp.core.config import ACPSettings
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy, WorkspaceSpec
from acp.workspaces.base import Workspace
from acp.workspaces.docker import DockerWorkspaceManager, docker_available
from acp.workspaces.factory import make_workspace_manager
from acp.workspaces.local import LocalWorkspaceManager

DOCKER = docker_available()


def _git_repo(tmp_path) -> Repository:
    src = tmp_path / "src"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    return Repository(name="d", local_path=str(src), default_branch="master")


def test_docker_run_argv_enforces_sandbox(tmp_path) -> None:
    mgr = DockerWorkspaceManager(tmp_path / "ws", image="python:3.11-slim",
                                 memory_mb=512, cpus=2.0, pids_limit=128)
    ws = Workspace(
        spec=WorkspaceSpec(repo_id="r", snapshot_id="s", base_commit="abc",
                           path=str(tmp_path / "ws/x"), branch="b", backend="docker",
                           policy=WorkspacePolicy(backend="docker", allow_network=False,
                                                  memory_mb=512, cpus=2.0, pids_limit=128)),
        path=tmp_path / "ws/x", backend="docker",
    )
    argv = mgr.docker_run_argv(ws, ["pytest", "-q"])
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "-m" in argv and "512m" in argv
    assert "--pids-limit" in argv and "128" in argv
    assert "-u" in argv  # non-root
    assert argv[-2:] == ["pytest", "-q"]
    assert "python:3.11-slim" in argv


def test_factory_falls_back_to_local_without_docker(tmp_path) -> None:
    settings = ACPSettings(enable_docker=True)
    mgr = make_workspace_manager(tmp_path / "ws", settings=settings)
    if not DOCKER:
        assert isinstance(mgr, LocalWorkspaceManager)


def test_factory_local_by_default(tmp_path) -> None:
    mgr = make_workspace_manager(tmp_path / "ws", settings=ACPSettings())
    assert isinstance(mgr, LocalWorkspaceManager)


@pytest.mark.skipif(not DOCKER, reason="docker not available")
def test_docker_workspace_create_and_cleanup(tmp_path) -> None:
    repo = _git_repo(tmp_path)
    mgr = DockerWorkspaceManager(tmp_path / "ws")
    base = Repo(repo.local_path).head.commit.hexsha
    snap = RepoSnapshot(repo_id=repo.id, base_commit=base)
    ws = mgr.create(repo, snap, WorkspacePolicy(backend="docker"))
    assert ws.path.exists()
    assert (ws.path / "calculator.py").exists()
    mgr.cleanup(ws, succeeded=True)
    assert not ws.path.exists()


@pytest.mark.skipif(not DOCKER, reason="docker not available")
def test_docker_workspace_no_network_runs(tmp_path) -> None:
    import subprocess

    repo = _git_repo(tmp_path)
    mgr = DockerWorkspaceManager(tmp_path / "ws")
    base = Repo(repo.local_path).head.commit.hexsha
    ws = mgr.create(repo, RepoSnapshot(repo_id=repo.id, base_commit=base),
                    WorkspacePolicy(backend="docker", allow_network=False))
    argv = mgr.docker_run_argv(ws, ["python", "-c", "print('hi')"])
    out = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0
    assert "hi" in out.stdout
    mgr.cleanup(ws)
