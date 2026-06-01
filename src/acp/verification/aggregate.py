"""Evidence aggregation (charter §14.5).

Combines a list of Evidence + diff context into an overall verification verdict
and risk signals used by the evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import EvidenceKind, EvidenceStatus, TaskType
from acp.schemas.verification import Evidence
from acp.schemas.workspace import DiffBundle


@dataclass
class AggregateVerdict:
    passed: bool
    security_risk: float = 0.0
    test_adequacy: float = 1.0
    review_burden: float = 0.0
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)


class EvidenceAggregator:
    def aggregate(
        self,
        evidence: list[Evidence],
        diff: DiffBundle | None = None,
        task_type: TaskType | str | None = None,
        diff_touches_tests: bool | None = None,
    ) -> AggregateVerdict:
        reasons: list[str] = []
        required_failed = False
        security_risk = 0.0
        considered = 0

        for ev in evidence:
            status = EvidenceStatus(ev.status) if isinstance(ev.status, str) else ev.status
            kind = EvidenceKind(ev.kind) if isinstance(ev.kind, str) else ev.kind
            if status == EvidenceStatus.SKIPPED:
                reasons.append(f"{ev.name} skipped: {ev.summary}")
                continue
            considered += 1
            if (
                kind in (EvidenceKind.UNIT_TEST, EvidenceKind.INTEGRATION_TEST)
                and status == EvidenceStatus.FAIL
            ):
                required_failed = True
                reasons.append(f"{ev.name} failed")
            if kind == EvidenceKind.SECURITY_SCAN and status == EvidenceStatus.FAIL:
                security_risk = max(security_risk, 0.9)
                reasons.append("security scan: high severity")
            if kind == EvidenceKind.STATIC_ANALYSIS and status == EvidenceStatus.FAIL:
                reasons.append(f"{ev.name} failed")
                required_failed = True

        # Test adequacy: bugfix without touching tests is suspicious (charter §14.5).
        test_adequacy = 1.0
        tt = TaskType(task_type) if isinstance(task_type, str) else task_type
        if tt in (TaskType.BUGFIX, TaskType.CI_FIX) and diff_touches_tests is False:
            test_adequacy = 0.4
            reasons.append("bugfix without test changes lowers test adequacy")

        # Review burden: large or scattered diffs.
        review_burden = 0.0
        if diff is not None:
            churn = diff.insertions + diff.deletions
            n_files = len(diff.changed_files)
            if churn > 400 or n_files > 15:
                review_burden = min(1.0, 0.3 + n_files / 50 + churn / 2000)
                reasons.append(f"large diff ({n_files} files, {churn} lines)")

        confidence = 1.0 if considered else 0.3
        if not considered:
            reasons.append("no objective evidence collected (low confidence)")

        return AggregateVerdict(
            passed=not required_failed,
            security_risk=security_risk,
            test_adequacy=test_adequacy,
            review_burden=review_burden,
            confidence=confidence,
            reasons=reasons,
        )
