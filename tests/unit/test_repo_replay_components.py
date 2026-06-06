"""Repo-replay verification components (Alpha 31)."""

from __future__ import annotations

import pytest

from acp.agents.repo_replay import REPLAY_TASKS
from acp.agents.repo_replay_components import (
    GitHubIssueIngestor,
    KnownFixVerifier,
    patch_equivalence,
    post_merge_replay,
    run_hidden_tests,
)

SEMVER = next(t for t in REPLAY_TASKS if t.name == "semver_compare").as_bench_task()


def test_known_fix_passes_hidden_tests() -> None:
    v = KnownFixVerifier().verify(SEMVER, SEMVER.fixed)
    assert v["passes_hidden_tests"] and v["behaves_like_known_fix"]


def test_buggy_patch_fails_hidden_tests() -> None:
    v = KnownFixVerifier().verify(SEMVER, SEMVER.buggy)
    assert not v["passes_hidden_tests"] and not v["behaves_like_known_fix"]


def test_patch_equivalence_functional_not_textual() -> None:
    # a different-but-correct fix is equivalent to the reference fix
    alt = SEMVER.fixed + "\n# an extra comment, behaviourally identical\n"
    eq = patch_equivalence(SEMVER, SEMVER.fixed, alt)
    assert eq["equivalent"]
    # the buggy patch is NOT equivalent to the fix
    assert not patch_equivalence(SEMVER, SEMVER.fixed, SEMVER.buggy)["equivalent"]


def test_post_merge_replay_outcomes() -> None:
    assert post_merge_replay(SEMVER, SEMVER.fixed)["post_merge_outcome"] == "held"
    assert post_merge_replay(SEMVER, SEMVER.buggy)["post_merge_outcome"] == "regression"
    assert post_merge_replay(SEMVER, None)["post_merge_outcome"] == "not_applied"


def test_hidden_tests_denominator() -> None:
    assert run_hidden_tests(SEMVER, SEMVER.fixed) is True
    assert run_hidden_tests(SEMVER, None) is False


def test_github_ingestor_is_honest_about_blocking() -> None:
    ing = GitHubIssueIngestor()
    assert not ing.available
    with pytest.raises(NotImplementedError):
        ing.ingest("https://github.com/x/y/issues/1")
