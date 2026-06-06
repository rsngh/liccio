"""Docker contention hardening: unique names + ACP labels (Alpha 22 WS3)."""

from __future__ import annotations

import pytest

from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy
from acp.workspaces.docker import DockerWorkspaceManager, docker_available


def _ws(tmp_path):
    import subprocess
    mgr = DockerWorkspaceManager(tmp_path / "ws")
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "init"]):
        subprocess.run(argv, cwd=src, check=False)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True,
                          text=True, check=False).stdout.strip()
    r = Repository(name="x", local_path=str(src), default_branch="master")
    return mgr, mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=base),
                           WorkspacePolicy(backend="docker"))


def test_run_argv_has_unique_name_and_acp_label(tmp_path) -> None:
    if not docker_available():
        pytest.skip("docker daemon not available")
    mgr, ws = _ws(tmp_path)
    a1 = mgr.docker_run_argv(ws, ["true"])
    a2 = mgr.docker_run_argv(ws, ["true"])
    assert "--rm" in a1 and "acp.managed=true" in a1
    n1 = a1[a1.index("--name") + 1]
    n2 = a2[a2.index("--name") + 1]
    assert n1.startswith("acp-run-") and n1 != n2  # unique per invocation


def test_prune_is_scoped_to_acp_label() -> None:
    import inspect
    src = inspect.getsource(DockerWorkspaceManager.prune_acp_resources)
    assert "label=acp.managed=true" in src  # never touches non-ACP containers
