"""Thin git helpers used by workspace managers."""

from __future__ import annotations

import contextlib
from pathlib import Path

from git import Repo

from acp.core.errors import WorkspaceError


def init_repo(path: Path) -> Repo:
    repo = Repo.init(path)
    return repo


def current_head(path: Path | str) -> str:
    return Repo(path).head.commit.hexsha


def is_dirty(path: Path | str) -> bool:
    repo = Repo(path)
    return repo.is_dirty(untracked_files=True)


def add_worktree(
    repo_path: Path | str, worktree_path: Path | str, commit: str, branch: str
) -> None:
    """Create a git worktree at ``worktree_path`` checked out to ``commit``."""
    repo = Repo(repo_path)
    try:
        repo.git.worktree("add", "-b", branch, str(worktree_path), commit)
    except Exception as exc:  # noqa: BLE001 - surface as typed error
        raise WorkspaceError(f"failed to create worktree: {exc}") from exc


def remove_worktree(repo_path: Path | str, worktree_path: Path | str) -> None:
    repo = Repo(repo_path)
    with contextlib.suppress(Exception):  # best-effort cleanup
        repo.git.worktree("remove", "--force", str(worktree_path))


def language_summary(path: Path | str) -> dict[str, int]:
    """Count files by extension as a coarse language summary."""
    exts: dict[str, int] = {}
    root = Path(path)
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            ext = p.suffix.lstrip(".") or "noext"
            exts[ext] = exts.get(ext, 0) + 1
    return dict(sorted(exts.items(), key=lambda kv: (-kv[1], kv[0])))
