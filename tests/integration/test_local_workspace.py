"""LocalWorkspaceManager + DiffCapturer tests (charter §9.1, §9.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from acp.schemas.repo import Repository, RepoSnapshot
from acp.workspaces.diff import DiffCapturer
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy


@pytest.fixture
def git_repo(tmp_path) -> Path:
    """A git repo with one committed file."""
    src = tmp_path / "src_repo"
    src.mkdir()
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    (src / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "README.md").write_text("# demo\n")
    repo.index.add(["calculator.py", "README.md"])
    repo.index.commit("initial")
    return src


def _repo_schema(path: Path) -> Repository:
    return Repository(name="demo", local_path=str(path), default_branch="master")


def test_create_workspace_and_isolated_worktree(tmp_path, git_repo) -> None:
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    repo = _repo_schema(git_repo)
    base = Repo(git_repo).head.commit.hexsha
    snap = RepoSnapshot(repo_id=repo.id, base_commit=base, branch="master")
    ws = mgr.create(repo, snap, default_policy())
    assert ws.path.exists()
    assert (ws.path / "calculator.py").exists()
    assert ws.spec.initial_head == base
    assert not mgr.dirty(ws)


def test_diff_new_modified_deleted(tmp_path, git_repo) -> None:
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    repo = _repo_schema(git_repo)
    base = Repo(git_repo).head.commit.hexsha
    snap = RepoSnapshot(repo_id=repo.id, base_commit=base)
    ws = mgr.create(repo, snap, default_policy())

    # modify, add, delete
    (ws.path / "calculator.py").write_text("def add(a, b):\n    return a + b + 1\n")
    (ws.path / "new_feature.py").write_text("x = 1\n")
    (ws.path / "README.md").unlink()

    bundle = mgr.capture_diff(ws, attempt_id="att_1")
    assert "calculator.py" in bundle.changed_files
    assert "new_feature.py" in bundle.added_files
    assert "README.md" in bundle.deleted_files
    assert bundle.insertions > 0
    assert bundle.deletions > 0
    assert not bundle.is_empty


def test_binary_detection(tmp_path, git_repo) -> None:
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    repo = _repo_schema(git_repo)
    base = Repo(git_repo).head.commit.hexsha
    snap = RepoSnapshot(repo_id=repo.id, base_commit=base)
    ws = mgr.create(repo, snap, default_policy())
    (ws.path / "blob.bin").write_bytes(b"\x00\x01\x02\x03binarydata")
    bundle = mgr.capture_diff(ws)
    assert "blob.bin" in bundle.binary_files


def test_diff_stats_match(tmp_path, git_repo) -> None:
    cap_path = tmp_path / "ws"
    mgr = LocalWorkspaceManager(cap_path)
    repo = _repo_schema(git_repo)
    base = Repo(git_repo).head.commit.hexsha
    snap = RepoSnapshot(repo_id=repo.id, base_commit=base)
    ws = mgr.create(repo, snap, default_policy())
    (ws.path / "calculator.py").write_text("def add(a, b):\n    return a + b\n\nZ = 9\n")
    cap = DiffCapturer(str(ws.path), base)
    stats = cap.get_diff_stats()
    assert stats["insertions"] >= 2


def test_cleanup_removes_worktree(tmp_path, git_repo) -> None:
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    repo = _repo_schema(git_repo)
    base = Repo(git_repo).head.commit.hexsha
    snap = RepoSnapshot(repo_id=repo.id, base_commit=base)
    ws = mgr.create(repo, snap, default_policy())
    assert ws.path.exists()
    mgr.cleanup(ws, succeeded=True)
    assert not ws.path.exists()
