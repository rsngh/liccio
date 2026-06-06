"""Repo-replay verification components (Alpha 31).

The pieces that make replay verification rigorous and tamper-proof:

- HiddenRegressionSuite / run_hidden_tests: the task's tests are the HELD-OUT verifier — the
  generator never sees them, so a patch can't pass by hard-coding outputs or deleting tests.
- KnownFixVerifier: does a candidate patch pass the hidden tests (i.e. behave like the known
  good fix)?
- patch_equivalence: are two patches FUNCTIONALLY equivalent (both pass the hidden suite)? —
  a candidate need not match the known fix textually, only behaviourally.
- post_merge_replay: simulate merging the patch and re-running the suite — the post-merge
  outcome (held, or introduced a regression).

Live GitHub issue ingestion (pre-fix snapshot + fixing PR + hidden tests from real history) is
network/auth-gated and not available here; ``GitHubIssueIngestor`` documents the contract a
real ingestor would satisfy and is fed by the same RepoReplayTask shape.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from acp.agents.benchmark_suite import build_bench_repo, run_pytest


def run_hidden_tests(bench_task, patch_content: str | None) -> bool:
    """Apply a patch to an isolated repo and run the HELD-OUT tests. The verifier denominator."""
    if patch_content is None:
        return False
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), bench_task)
        (repo / bench_task.module_path).write_text(patch_content)
        return run_pytest(repo)


@dataclass
class KnownFixVerifier:
    """Verify a candidate patch against the task's known-good behaviour (hidden tests)."""

    def verify(self, bench_task, patch_content: str | None) -> dict:
        passes = run_hidden_tests(bench_task, patch_content)
        known_passes = run_hidden_tests(bench_task, bench_task.fixed)
        return {"passes_hidden_tests": passes,
                "known_fix_passes": known_passes,
                "behaves_like_known_fix": passes and known_passes}


def patch_equivalence(bench_task, patch_a: str | None, patch_b: str | None) -> dict:
    """Two patches are FUNCTIONALLY equivalent iff both pass the hidden suite."""
    a = run_hidden_tests(bench_task, patch_a)
    b = run_hidden_tests(bench_task, patch_b)
    return {"a_passes": a, "b_passes": b, "equivalent": a and b}


def post_merge_replay(bench_task, patch_content: str | None) -> dict:
    """Simulate merging the patch + re-running the suite: did the fix hold or regress?"""
    applies = patch_content is not None
    held = run_hidden_tests(bench_task, patch_content)
    return {"applies": applies, "hidden_tests_pass": held,
            "post_merge_outcome": ("held" if held else
                                   ("regression" if applies else "not_applied"))}


@dataclass
class GitHubIssueIngestor:
    """Contract for a real GitHub issue -> RepoReplayTask ingestor (env-blocked here).

    A live ingestor would resolve: issue text, the pre-fix commit (checkout), the known fixing
    commit/PR (the reference fix), and a test command (the hidden regression suite). With no
    network/auth in this environment it raises on ingest; the interface is fixed so a real
    implementation drops in. Offline replay uses RepoReplayTask directly.
    """
    available: bool = False

    def ingest(self, issue_url: str) -> dict:
        raise NotImplementedError(
            "live GitHub ingest needs network/auth; use RepoReplayTask offline replay")
