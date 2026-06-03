"""Harness evolution pipeline (Alpha 11/12, WS7).

A harness's prompt/config can be *improved* from execution evidence, but a
persistent change to how every future run behaves is high-risk. This pipeline
gates such updates: an evolver proposes a diff, it is redaction/security-scanned,
run through regression + negative-transfer evals, human-reviewed, canaried, and
only then promoted — with a recorded rollback. The contract enforced here:

    no HarnessUpdate may be promoted without an eval, an audit trail, and a
    rollback plan.

The flow is represented as explicit stages so the audit trail is inspectable; the
actual prompt edits are opaque to this module (it governs, it does not author).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from acp.core.redaction import Redactor


@dataclass
class HarnessUpdateProposal:
    harness_name: str
    rationale: str
    proposed_diff: str  # the prompt/config change (text)
    evidence_run_ids: list[str] = field(default_factory=list)


@dataclass
class HarnessUpdateDiff:
    redacted_diff: str
    secrets_found: int
    security_flags: list[str] = field(default_factory=list)


@dataclass
class HarnessUpdateEval:
    regression_passed: bool
    negative_transfer_passed: bool  # didn't degrade other task types
    baseline_score: float
    candidate_score: float

    @property
    def improves(self) -> bool:
        return self.candidate_score > self.baseline_score


@dataclass
class HarnessUpdateReview:
    approved: bool
    reviewer: str = ""
    notes: str = ""


@dataclass
class HarnessUpdateCanary:
    stages: list[float] = field(default_factory=lambda: [0.05, 0.25, 1.0])
    rolled_back: bool = False
    stopped_at: float | None = None


@dataclass
class HarnessUpdateRollback:
    plan: str
    previous_version: str


@dataclass
class HarnessUpdateDecision:
    harness_name: str
    promoted: bool
    blocked_reasons: list[str]
    diff: HarnessUpdateDiff
    evaluation: HarnessUpdateEval | None
    review: HarnessUpdateReview | None
    canary: HarnessUpdateCanary | None
    rollback: HarnessUpdateRollback | None

    def as_dict(self) -> dict:
        return {
            "harness_name": self.harness_name, "promoted": self.promoted,
            "blocked_reasons": self.blocked_reasons,
            "diff": {"secrets_found": self.diff.secrets_found,
                     "security_flags": self.diff.security_flags},
            "evaluation": (None if self.evaluation is None else {
                "regression_passed": self.evaluation.regression_passed,
                "negative_transfer_passed": self.evaluation.negative_transfer_passed,
                "improves": self.evaluation.improves}),
            "review_approved": None if self.review is None else self.review.approved,
            "rollback_present": self.rollback is not None,
            "canary_rolled_back": None if self.canary is None else self.canary.rolled_back,
        }


_SECRET_SHAPE = re.compile(r"\b(sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9]{8,}\b")


def scan_diff(proposal: HarnessUpdateProposal) -> HarnessUpdateDiff:
    """Redact secrets + flag suspicious instructions in a proposed prompt diff."""
    redactor = Redactor()
    redacted = redactor.redact_text(proposal.proposed_diff)
    secrets = len(_SECRET_SHAPE.findall(proposal.proposed_diff))
    if secrets:
        redacted = _SECRET_SHAPE.sub("[REDACTED]", redacted)
    flags: list[str] = []
    low = proposal.proposed_diff.lower()
    for pat, flag in (("ignore previous", "prompt_injection"),
                      ("disable verification", "disable_verification"),
                      ("skip tests", "skip_tests"),
                      ("exfiltrate", "exfiltration")):
        if pat in low:
            flags.append(flag)
    return HarnessUpdateDiff(redacted_diff=redacted, secrets_found=secrets,
                             security_flags=flags)


def evaluate_update(
    proposal: HarnessUpdateProposal,
    *,
    diff: HarnessUpdateDiff,
    evaluation: HarnessUpdateEval | None = None,
    review: HarnessUpdateReview | None = None,
    canary: HarnessUpdateCanary | None = None,
    rollback: HarnessUpdateRollback | None = None,
) -> HarnessUpdateDecision:
    """Apply the promotion contract. Promotion requires: clean security scan,
    a passing improving eval, an approving review, a rollback plan, and a canary
    that did not roll back."""
    reasons: list[str] = []
    if diff.security_flags or diff.secrets_found:
        reasons.append("security/redaction flags in proposed diff")
    if evaluation is None:
        reasons.append("no eval (regression + negative-transfer) provided")
    else:
        if not evaluation.regression_passed:
            reasons.append("regression eval failed")
        if not evaluation.negative_transfer_passed:
            reasons.append("negative-transfer eval failed (degraded other tasks)")
        if not evaluation.improves:
            reasons.append("candidate does not beat baseline")
    if review is None or not review.approved:
        reasons.append("no approving human review")
    if rollback is None:
        reasons.append("no rollback plan")
    if canary is not None and canary.rolled_back:
        reasons.append("canary rolled back")
    promoted = not reasons
    return HarnessUpdateDecision(
        harness_name=proposal.harness_name, promoted=promoted,
        blocked_reasons=reasons, diff=diff, evaluation=evaluation,
        review=review, canary=canary, rollback=rollback)
