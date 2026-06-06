"""Report-truth chaos (Round 25 test G): corrupting any count must fail the strict gate.

The review wants production health treated as a CONTRACT, not a report: deliberately
corrupting the artifact count / pytest count / source count must be caught by
`acp reports sync-status --strict` (and therefore the report_truth_consistent health gate).
This asserts each corruption is detected and that a consistent document passes.
"""

from __future__ import annotations

from acp.observability.release_truth import ReleaseTruth, check_status_consistency

TRUTH = ReleaseTruth(source_files=285, artifacts=90, tests_passed=1131, tests_skipped=5)
GOOD = "1131 passing, 5 skipped; 285 source files; 90 artifacts valid"


def test_consistent_document_passes() -> None:
    assert check_status_consistency(GOOD, TRUTH) == []


def test_corrupt_test_count_is_caught() -> None:
    bad = "999 passing, 5 skipped; 285 source files; 90 artifacts valid"
    problems = check_status_consistency(bad, TRUTH)
    assert any("test count" in p for p in problems)


def test_corrupt_source_count_is_caught() -> None:
    bad = "1131 passing, 5 skipped; 100 source files; 90 artifacts valid"
    problems = check_status_consistency(bad, TRUTH)
    assert any("source files" in p for p in problems)


def test_corrupt_artifact_count_is_caught() -> None:
    bad = "1131 passing, 5 skipped; 285 source files; 46 artifacts valid"
    problems = check_status_consistency(bad, TRUTH)
    assert any("artifacts" in p for p in problems)


def test_missing_count_lines_are_caught() -> None:
    assert check_status_consistency("no counts here at all", TRUTH)  # several problems


def test_all_three_corruptions_caught_together() -> None:
    bad = "1 passing, 5 skipped; 1 source files; 1 artifacts valid"
    problems = check_status_consistency(bad, TRUTH)
    assert len(problems) >= 3  # test, source, AND artifact drift all reported
