"""Git diff capture utilities (charter §9.3).

Operates on a git working tree via GitPython. Produces a ``DiffBundle`` plus
fine-grained helpers used by tests and verification.
"""

from __future__ import annotations

from git import Repo

from acp.schemas.workspace import DiffBundle


class DiffCapturer:
    """Captures diffs of a working tree against a base commit."""

    def __init__(self, repo_path: str, base_commit: str | None = None) -> None:
        self.repo = Repo(repo_path)
        self.base_commit = base_commit or self.repo.head.commit.hexsha

    def _diff_index(self):
        # Diff base commit against the working tree (including untracked).
        return self.repo.commit(self.base_commit).diff(None)

    def get_changed_files(self) -> list[str]:
        changed = {d.a_path or d.b_path for d in self._diff_index()}
        changed.update(self.repo.untracked_files)
        return sorted(p for p in changed if p)

    def get_unified_diff(self) -> str:
        # Tracked changes.
        tracked = self.repo.git.diff(self.base_commit)
        # Untracked files: show as added.
        parts = [tracked] if tracked else []
        wtd = str(self.repo.working_tree_dir or "")
        for path in self.repo.untracked_files:
            try:
                content = f"{wtd}/{path}"
                with open(content, encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
                added = "\n".join(f"+{line}" for line in body.splitlines())
                parts.append(
                    f"diff --git a/{path} b/{path}\nnew file\n--- /dev/null\n+++ b/{path}\n{added}"
                )
            except (OSError, UnicodeDecodeError):
                parts.append(f"diff --git a/{path} b/{path}\nnew file (binary)")
        return "\n".join(parts)

    def get_diff_stats(self) -> dict[str, int]:
        insertions = deletions = 0
        for line in self.get_unified_diff().splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                insertions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        return {"insertions": insertions, "deletions": deletions}

    def get_file_patch(self, path: str) -> str:
        return self.repo.git.diff(self.base_commit, "--", path)

    def detect_binary_changes(self) -> list[str]:
        binary: list[str] = []
        for d in self._diff_index():
            path = d.a_path or d.b_path
            try:
                blob = d.b_blob or d.a_blob
                if path and blob is not None and b"\x00" in blob.data_stream.read(1024):
                    binary.append(path)
            except (OSError, ValueError):
                continue
        # untracked binaries
        wtd = self.repo.working_tree_dir or ""
        for path in self.repo.untracked_files:
            try:
                with open(f"{wtd}/{path}", "rb") as fh:
                    if b"\x00" in fh.read(1024):
                        binary.append(path)
            except OSError:
                continue
        return sorted(set(binary))

    def categorize(self) -> tuple[list[str], list[str], list[str]]:
        """Return (added, modified, deleted) tracked paths."""
        added, modified, deleted = [], [], []
        for d in self._diff_index():
            path = d.a_path or d.b_path
            if path is None:
                continue
            if d.new_file:
                added.append(path)
            elif d.deleted_file:
                deleted.append(path)
            else:
                modified.append(path)
        added.extend(self.repo.untracked_files)
        return sorted(set(added)), sorted(set(modified)), sorted(set(deleted))

    def build_bundle(self, attempt_id: str | None = None) -> DiffBundle:
        added, _modified, deleted = self.categorize()
        stats = self.get_diff_stats()
        return DiffBundle(
            attempt_id=attempt_id,
            base_commit=self.base_commit,
            changed_files=self.get_changed_files(),
            added_files=added,
            deleted_files=deleted,
            binary_files=self.detect_binary_changes(),
            insertions=stats["insertions"],
            deletions=stats["deletions"],
            unified_diff=self.get_unified_diff(),
        )
