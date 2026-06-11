# ruff: noqa: E501
"""DiffCache — repo-level verified-fix cache for the PRODUCTION loop (generalizes SolutionStore).

SolutionStore caches a fixed *function/module* (great for the single-module eval bundles). The
production runner works on arbitrary multi-file repos, so the right primitive is a **unified-diff
cache**: store the verified patch for a `(repo_id, failure_signature)` and, on recurrence, `git apply`
it into a fresh workspace. The cached fix then flows through the EXISTING capture-diff → verification
nodes — so it is re-verified, never blind-trusted, and a clean apply that passes the repo's checks is
a solved run with ZERO agent calls. Drift (apply fails / verify fails) falls back to the live agents.

Keyed by (tenant, repo_id, failure_signature); trust-gated (only verified diffs admitted). The
failure_signature is supplied by the caller (e.g. CI knows the failing-test id when it files the task);
absent it, the cache simply never fires. Deterministic, dependency-free except `git apply` via subprocess.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DiffRecord:
    repo_id: str
    failure_signature: str
    unified_diff: str
    tenant: str = "tenant_a"
    verified: bool = True
    created_at: float = 0.0


@dataclass
class DiffCache:
    """Tenant-isolated cache of verified unified diffs, keyed by (repo_id, failure_signature)."""

    records: list[DiffRecord] = field(default_factory=list)

    def record(self, *, repo_id: str, failure_signature: str, unified_diff: str,
               tenant: str = "tenant_a", verified: bool, now: float = 0.0) -> bool:
        """Admit a fix ONLY if it verified and the diff is non-empty."""
        if not verified or not unified_diff.strip() or not failure_signature:
            return False
        self.records.append(DiffRecord(repo_id=repo_id, failure_signature=failure_signature,
                                       unified_diff=unified_diff, tenant=tenant, verified=True,
                                       created_at=now))
        return True

    def recall(self, *, tenant: str, repo_id: str, failure_signature: str) -> DiffRecord | None:
        """Most-recent verified diff for this exact (repo_id, failure_signature), tenant-scoped."""
        hits = [r for r in self.records if r.tenant == tenant and r.repo_id == repo_id
                and r.failure_signature == failure_signature and r.verified]
        return max(hits, key=lambda r: r.created_at) if hits else None

    def can_apply(self, *, workspace: Path, unified_diff: str) -> bool:
        """True iff the cached diff applies cleanly to the workspace (no drift) — `git apply --check`."""
        return self._git_apply(workspace, unified_diff, check_only=True)

    def replay(self, *, tenant: str, repo_id: str, failure_signature: str, workspace: Path) -> bool:
        """Recall the cached diff and APPLY it into the workspace. Returns True iff a hit applied
        cleanly (the workspace now holds the cached fix, to be re-verified by the caller). A miss or a
        drifted patch returns False -> caller runs the live agents."""
        rec = self.recall(tenant=tenant, repo_id=repo_id, failure_signature=failure_signature)
        if rec is None or not self.can_apply(workspace=workspace, unified_diff=rec.unified_diff):
            return False
        return self._git_apply(workspace, rec.unified_diff, check_only=False)

    @staticmethod
    def _git_apply(workspace: Path, unified_diff: str, *, check_only: bool) -> bool:
        args = ["git", "-C", str(workspace), "apply", "--whitespace=nowarn"]
        if check_only:
            args.append("--check")
        try:
            r = subprocess.run(args, input=unified_diff, capture_output=True, text=True,
                               timeout=30, check=False)
        except (subprocess.TimeoutExpired, OSError):
            return False
        return r.returncode == 0
