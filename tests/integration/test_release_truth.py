"""Report-truth hard gate (Alpha 25, test A).

Fails if CURRENT_STATUS.md disagrees with the canonical counts computed from the
authoritative sources (source-file count, artifact manifest, committed pytest report).
This makes report drift — the recurring product bug — impossible to commit.
"""

from __future__ import annotations

from pathlib import Path

from acp.observability.release_truth import (
    ReleaseTruth,
    check_status_consistency,
    gather_truth,
    sync_status_text,
)

ROOT = Path(__file__).resolve().parents[2]


def test_current_status_agrees_with_release_truth() -> None:
    truth = gather_truth(ROOT)
    status = (ROOT / "CURRENT_STATUS.md").read_text()
    problems = check_status_consistency(status, truth)
    assert problems == [], f"CURRENT_STATUS drift: {problems}"


def test_truth_counts_are_sane() -> None:
    truth = gather_truth(ROOT)
    assert truth.source_files > 200          # the codebase is large
    assert truth.artifacts > 50              # many committed artifacts
    assert truth.tests_passed > 1000


def test_sync_fixes_a_drifted_document() -> None:
    truth = ReleaseTruth(source_files=279, artifacts=84, tests_passed=1063, tests_skipped=5)
    drifted = ("Tests: 999 passing, 0 skipped; clean across 100 source files; "
               "(46 artifacts valid).")
    assert check_status_consistency(drifted, truth)         # drift detected
    fixed = sync_status_text(drifted, truth)
    assert check_status_consistency(fixed, truth) == []     # sync repairs it


def test_check_detects_each_kind_of_drift() -> None:
    truth = ReleaseTruth(source_files=279, artifacts=84, tests_passed=1063, tests_skipped=5)
    ok = "1063 passing, 5 skipped; 279 source files; 84 artifacts valid"
    assert check_status_consistency(ok, truth) == []
    assert check_status_consistency("279 source files; 84 artifacts valid", truth)  # no tests
    assert check_status_consistency(
        "1063 passing, 5 skipped; 84 artifacts valid", truth)  # no source count
