"""Local-vs-Docker record parity + persisted bandit MC (round-3 R3-8)."""

from __future__ import annotations

import sys

import pytest

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.schemas.workspace import CommandRunRecord, WorkspacePolicy, WorkspaceSpec
from acp.workspaces.base import Workspace
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.docker import DockerWorkspaceManager
from acp.workspaces.docker_runner import DockerCommandRunner


class _FakeHost:
    def run(self, argv, cwd, timeout_s=None, allow_cwd_outside_root=False,
            attempt_id=None, trace_id=None, **kw):
        return CommandRunRecord(argv=argv, cwd=str(cwd), exit_code=0, stdout_summary="ok")


def test_local_docker_record_parity(tmp_path) -> None:
    # local execution
    local = CommandRunner(allowed_root=tmp_path)
    local_rec = local.run([sys.executable, "-c", "print('hi')"], cwd=tmp_path)
    # docker execution (fake host) records the SAME logical command + workspace cwd
    mgr = DockerWorkspaceManager(tmp_path / "root")
    ws = Workspace(
        spec=WorkspaceSpec(repo_id="r", snapshot_id="s", base_commit="abc",
                           path=str(tmp_path / "ws"), branch="b", backend="docker",
                           policy=WorkspacePolicy(backend="docker")),
        path=tmp_path / "ws", backend="docker",
    )
    docker = DockerCommandRunner(mgr, ws, host_runner=_FakeHost())
    docker_rec = docker.run([sys.executable, "-c", "print('hi')"])
    # parity: same logical argv recorded; docker normalizes cwd to /workspace
    assert docker_rec.argv == local_rec.argv == [sys.executable, "-c", "print('hi')"]
    assert docker_rec.cwd == "/workspace"
    assert docker_rec.resource_usage.get("backend") == "docker"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'mc.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def test_bandit_monte_carlo_persisted(service) -> None:
    run = service.run_bandit_mc_eval(seeds=10, rounds=200)
    assert run.kind == "bandit_monte_carlo"
    assert run.summary["beats_random"] is True
    assert run.summary["wins_vs_random"] >= 8
    # durable
    fresh = AppService(service.settings)
    assert fresh.get_eval_run(run.id)["kind"] == "bandit_monte_carlo"
    report = fresh.get_eval_report(run.id)
    assert "mean_margin" in report["content"]
