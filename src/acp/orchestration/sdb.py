"""Stochastic–deterministic boundary (SDB) contracts (Alpha 24 area 8).

Production Agent Architecture methodology: every stochastic output crosses a typed boundary
— propose -> verify -> commit | reject — before it affects the system. The proposer is
stochastic (an LLM patch, skill edit, routing promotion, advisor advice, memory write); the
verifier and commit gate are DETERMINISTIC. Nothing commits without passing every required
verifier, and every rejection carries a typed reason. This formalizes, in one place, the
invariant ACP already enforces piecemeal (measured gain before deploy, poison blocked,
contaminated attempts never train).

A contract binds a proposal KIND to its required verifiers; ``run_contract`` executes them
and returns a ``CommitRecord`` audit trail (committed bool + typed reject reasons + a
partial-result policy outcome when a deadline/retry budget is hit).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

PROPOSAL_KINDS = (
    "code_patch", "skill_edit", "harness_patch", "routing_promotion",
    "advisor_advice", "memory_write", "context_update",
)
REJECT_REASONS = (
    "verification_failed", "measurement_untrusted", "poison_detected",
    "no_measured_gain", "budget_exceeded", "deadline_partial", "policy_violation",
)


@dataclass
class Proposal:
    kind: str
    payload: dict = field(default_factory=dict)
    proposer: str = "unknown"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in PROPOSAL_KINDS:
            raise ValueError(f"unknown proposal kind {self.kind}")


@dataclass
class VerificationResult:
    name: str
    passed: bool
    reject_reason: str | None = None     # one of REJECT_REASONS when not passed
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.passed and self.reject_reason not in REJECT_REASONS:
            raise ValueError(f"failed verifier needs a typed reject_reason: {self.name}")


# A verifier is a deterministic function proposal -> VerificationResult.
Verifier = Callable[[Proposal], VerificationResult]


@dataclass
class PartialResultPolicy:
    """What to do when a deadline/retry budget is hit before verification completes."""
    on_deadline: str = "reject"          # reject | commit_partial | retry
    max_retries: int = 0


@dataclass
class CommitRecord:
    kind: str
    proposer: str
    committed: bool
    reject_reasons: list = field(default_factory=list)
    verifications: list = field(default_factory=list)   # list[VerificationResult dicts]
    partial: bool = False

    def to_dict(self) -> dict:
        return {"kind": self.kind, "proposer": self.proposer, "committed": self.committed,
                "reject_reasons": self.reject_reasons, "partial": self.partial,
                "verifications": self.verifications}


# Registry: proposal kind -> ordered required verifier names (documentation/audit aid).
@dataclass
class SDBContract:
    kind: str
    verifiers: list                      # list[Verifier]
    partial_policy: PartialResultPolicy = field(default_factory=PartialResultPolicy)


def run_contract(contract: SDBContract, proposal: Proposal, *,
                 deadline_hit: bool = False) -> CommitRecord:
    """Execute the contract's verifiers; commit only if ALL pass. Typed rejects on failure.

    ``deadline_hit`` simulates the deterministic deadline/retry boundary: the partial-result
    policy decides whether a deadline rejects, commits a partial, or would retry.
    """
    if proposal.kind != contract.kind:
        raise ValueError(f"proposal {proposal.kind} != contract {contract.kind}")
    record = CommitRecord(kind=proposal.kind, proposer=proposal.proposer, committed=False)

    if deadline_hit:
        record.partial = True
        if contract.partial_policy.on_deadline == "commit_partial":
            record.committed = True
            return record
        record.reject_reasons.append("deadline_partial")
        return record

    all_passed = True
    for verifier in contract.verifiers:
        result = verifier(proposal)
        record.verifications.append({"name": result.name, "passed": result.passed,
                                     "reject_reason": result.reject_reason,
                                     "detail": result.detail})
        if not result.passed:
            all_passed = False
            if result.reject_reason and result.reject_reason not in record.reject_reasons:
                record.reject_reasons.append(result.reject_reason)
    record.committed = all_passed
    return record
