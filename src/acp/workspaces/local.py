"""Local git-worktree workspace manager (charter §9.1).

Each run gets an isolated git worktree checked out to the snapshot's base commit
on a fresh branch. We capture initial/final HEAD and can produce a diff against
the base. Cleanup honors the workspace policy.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from git import Repo

from acp.core.errors import WorkspaceError
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy, WorkspaceSpec
from acp.workspaces.base import Workspace
from acp.workspaces.diff import DiffCapturer
from acp.workspaces.git_ops import add_worktree, is_dirty, remove_worktree


class LocalWorkspaceManager:
    backend = "local"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(
        self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy
    ) -> Workspace:
        if not repo.local_path:
            raise WorkspaceError(f"repository {repo.id} has no local_path")
        source = Path(repo.local_path).resolve()
        if not (source / ".git").exists():
            raise WorkspaceError(f"{source} is not a git repository")

        ws_id = f"ws_{uuid.uuid4().hex[:12]}"
        ws_path = self.root / ws_id
        branch = f"acp/{ws_id}"
        add_worktree(source, ws_path, snapshot.base_commit, branch)

        head = Repo(ws_path).head.commit.hexsha
        spec = WorkspaceSpec(
            id=ws_id,
            repo_id=repo.id,
            snapshot_id=snapshot.id,
            base_commit=snapshot.base_commit,
            path=str(ws_path),
            branch=branch,
            backend=self.backend,
            policy=policy,
            initial_head=head,
        )
        return Workspace(spec=spec, path=ws_path, backend=self.backend)

    def capture_diff(self, workspace: Workspace, attempt_id: str | None = None):
        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        return cap.build_bundle(attempt_id=attempt_id)

    def dirty(self, workspace: Workspace) -> bool:
        return is_dirty(workspace.path)

    def final_head(self, workspace: Workspace) -> str:
        return Repo(workspace.path).head.commit.hexsha

    def cleanup(self, workspace: Workspace, *, succeeded: bool = True) -> None:
        policy = workspace.spec.policy.cleanup
        should = policy == "always" or (policy == "on_success" and succeeded)
        if not should:
            return
        source = workspace.metadata.get("source_repo")
        # Remove via the source repo's worktree command if we know it; else best
        # effort by deleting the directory.
        if source:
            remove_worktree(source, workspace.path)
        else:
            try:
                # Find source from the worktree's gitdir link.
                repo = Repo(workspace.path)
                common = Path(repo.common_dir).resolve()
                # common_dir is <source>/.git/worktrees/<id>; source is 3 up.
                source_repo = common.parent.parent.parent
                remove_worktree(source_repo, workspace.path)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                import shutil

                shutil.rmtree(workspace.path, ignore_errors=True)
