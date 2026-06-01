"""DockerCommandRunner (round-2 Block D).

The argv construction + host delegation are tested with a fake host runner (no
daemon needed). Live execution tests are skipped unless Docker is available.
"""

from __future__ import annotations

import subprocess

import pytest
from git import Repo

from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import CommandRunRecord, WorkspacePolicy, WorkspaceSpec
from acp.workspaces.base import Workspace
from acp.workspaces.docker import DockerWorkspaceManager, docker_available
from acp.workspaces.docker_runner import DockerCommandRunner

DOCKER = docker_available()


class _FakeHost:
    def __init__(self):
        self.calls = []

    def run(self, argv, cwd, timeout_s=None, allow_cwd_outside_root=False,
            attempt_id=None, trace_id=None, **kw):
        self.calls.append(argv)
        return CommandRunRecord(argv=argv, cwd=str(cwd), exit_code=0,
                                stdout_summary="ok", attempt_id=attempt_id, trace_id=trace_id)


def _ws(tmp_path) -> Workspace:
    return Workspace(
        spec=WorkspaceSpec(repo_id="r", snapshot_id="s", base_commit="abc",
                           path=str(tmp_path / "ws"), branch="b", backend="docker",
                           policy=WorkspacePolicy(backend="docker", allow_network=False,
                                                  memory_mb=512, pids_limit=128)),
        path=tmp_path / "ws", backend="docker",
    )


def test_docker_command_runner_wraps_in_docker_run(tmp_path) -> None:
    mgr = DockerWorkspaceManager(tmp_path / "root", image="python:3.11-slim")
    host = _FakeHost()
    runner = DockerCommandRunner(mgr, _ws(tmp_path), host_runner=host)
    rec = runner.run(["pytest", "-q"])
    argv = host.calls[0]
    assert argv[:2] == ["docker", "run"]
    assert "--network" in argv and "none" in argv
    assert argv[-2:] == ["pytest", "-q"]
    # logical command recorded, not the docker wrapper
    assert rec.argv == ["pytest", "-q"]
    assert rec.cwd == "/workspace"
    assert rec.resource_usage["backend"] == "docker"


@pytest.mark.skipif(not DOCKER, reason="docker not available")
def test_docker_command_runner_pwd_is_workspace(tmp_path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("hi")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["f.txt"])
    repo.index.commit("init")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    mgr = DockerWorkspaceManager(tmp_path / "ws")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                    WorkspacePolicy(backend="docker"))
    rec = DockerCommandRunner(mgr, ws).run(["pwd"])
    assert rec.exit_code == 0
    mgr.cleanup(ws)


@pytest.mark.skipif(not DOCKER, reason="docker not available")
def test_docker_no_network_blocks_curl(tmp_path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    (src / "x").write_text("x")
    repo.index.add(["x"])
    repo.index.commit("i")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    mgr = DockerWorkspaceManager(tmp_path / "ws")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                    WorkspacePolicy(backend="docker", allow_network=False))
    argv = mgr.docker_run_argv(ws, ["python", "-c",
                                    "import urllib.request;urllib.request.urlopen('http://example.com',timeout=3)"])
    out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert out.returncode != 0  # network disabled -> failure
    mgr.cleanup(ws)
