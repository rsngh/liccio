"""Evidence parsing + aggregation tests (charter §14.5, §14.6)."""

from __future__ import annotations

from acp.core.enums import EvidenceKind, EvidenceStatus, TaskType
from acp.schemas.verification import Evidence
from acp.schemas.workspace import DiffBundle
from acp.verification.aggregate import EvidenceAggregator
from acp.verification.runners import PytestRunner


def test_pytest_parse_pass() -> None:
    passed, failed, skipped, errors = PytestRunner._parse("3 passed in 0.1s")
    assert (passed, failed, skipped, errors) == (3, 0, 0, 0)


def test_pytest_parse_fail() -> None:
    passed, failed, skipped, errors = PytestRunner._parse("1 failed, 2 passed in 0.2s")
    assert failed == 1 and passed == 2


def _ev(kind: EvidenceKind, status: EvidenceStatus, name="x") -> Evidence:
    return Evidence(task_id="t", kind=kind, name=name, status=status)


def test_required_test_failure_fails_verification() -> None:
    v = EvidenceAggregator().aggregate([_ev(EvidenceKind.UNIT_TEST, EvidenceStatus.FAIL)])
    assert v.passed is False


def test_security_high_raises_risk() -> None:
    v = EvidenceAggregator().aggregate([_ev(EvidenceKind.SECURITY_SCAN, EvidenceStatus.FAIL)])
    assert v.security_risk >= 0.9


def test_missing_command_skipped_not_pass() -> None:
    v = EvidenceAggregator().aggregate([_ev(EvidenceKind.UNIT_TEST, EvidenceStatus.SKIPPED)])
    # skipped contributes no objective evidence -> low confidence, not a pass signal
    assert v.confidence < 0.5
    assert v.passed is True  # nothing failed, but confidence is low


def test_bugfix_without_test_change_lowers_adequacy() -> None:
    v = EvidenceAggregator().aggregate(
        [_ev(EvidenceKind.UNIT_TEST, EvidenceStatus.PASS)],
        task_type=TaskType.BUGFIX,
        diff_touches_tests=False,
    )
    assert v.test_adequacy < 0.5


def test_large_diff_raises_review_burden() -> None:
    diff = DiffBundle(changed_files=[f"f{i}.py" for i in range(20)], insertions=600, deletions=50)
    v = EvidenceAggregator().aggregate(
        [_ev(EvidenceKind.UNIT_TEST, EvidenceStatus.PASS)], diff=diff
    )
    assert v.review_burden > 0.0
