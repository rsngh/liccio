"""Guarded PR pipeline (Alpha 32)."""

from __future__ import annotations

from acp.agents.benchmark_suite import BENCH_TASKS, build_bench_repo
from acp.orchestration.guarded_pr import (
    PROTECTED_BRANCHES,
    build_draft_pr,
    safe_branch_name,
)

DIVIDE = next(t for t in BENCH_TASKS if t.name == "divide")


def _git(repo, *a):
    import subprocess
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True,
                          check=False).stdout.strip()


def test_safe_branch_name_never_protected() -> None:
    for name in ("main", "master", "production"):
        assert safe_branch_name(name).split("/")[-1] not in PROTECTED_BRANCHES


def test_verified_draft_applied_to_feature_branch_not_protected(tmp_path) -> None:
    repo = build_bench_repo(tmp_path, DIVIDE)
    base = _git(repo, "rev-parse", "HEAD")
    pr = build_draft_pr(repo, task_id="divide", issue_text="divide adds instead of divides",
                        module_path=DIVIDE.module_path, patch_content=DIVIDE.fixed,
                        verified=True, base_branch="master")
    assert pr.applied_to_branch and not pr.targeted_protected_branch
    assert pr.branch == "acp/draft-divide"
    assert pr.rollback is not None and "verified in sandbox" in pr.description
    # the protected branch (master) HEAD is unchanged — no write to a protected branch
    assert _git(repo, "rev-parse", "master") == base
    assert pr.head_commit != base


def test_unverified_draft_is_blocked(tmp_path) -> None:
    repo = build_bench_repo(tmp_path, DIVIDE)
    pr = build_draft_pr(repo, task_id="divide", issue_text="x",
                        module_path=DIVIDE.module_path, patch_content=DIVIDE.buggy,
                        verified=False)
    assert not pr.applied_to_branch and "not verified" in pr.blocked_reason
    assert "NOT verified" in pr.description


def test_pr_description_has_issue_and_status(tmp_path) -> None:
    repo = build_bench_repo(tmp_path, DIVIDE)
    pr = build_draft_pr(repo, task_id="divide", issue_text="the divide bug",
                        module_path=DIVIDE.module_path, patch_content=DIVIDE.fixed,
                        verified=True)
    assert "the divide bug" in pr.description and "Draft fix: divide" in pr.description
