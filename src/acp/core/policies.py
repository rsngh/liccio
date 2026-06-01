"""Governance policy engine (charter §22).

Pure-decision policies plus an in-memory audit log. Defaults are safe: no
auto-merge, no network, no secrets, human review for high/critical risk,
experimental policies cannot auto-approve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import RiskLevel
from acp.core.errors import PolicyViolation
from acp.core.time import utcnow
from acp.schemas.trace import AuditEvent


@dataclass
class GovernanceDefaults:
    auto_merge: bool = False
    allow_network: bool = False
    inject_secrets: bool = False
    max_cost_usd: float = 5.0
    max_parallelism: int = 4


class AuditLog:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event_type: str, *, actor: str = "system", target: str | None = None,
               detail: dict | None = None, trace_id: str | None = None) -> AuditEvent:
        ev = AuditEvent(
            event_type=event_type, actor=actor, target=target,
            detail=detail or {}, trace_id=trace_id, created_at=utcnow(),
        )
        self.events.append(ev)
        return ev


@dataclass
class PolicyEngine:
    defaults: GovernanceDefaults = field(default_factory=GovernanceDefaults)
    audit: AuditLog = field(default_factory=AuditLog)

    # --- RiskPolicy / HumanApprovalPolicy ---
    def requires_human_review(self, risk: RiskLevel) -> bool:
        return risk.requires_human_review()

    def check_auto_finalize(self, risk: RiskLevel, *, experimental: bool, trace_id=None) -> None:
        if risk.requires_human_review():
            raise PolicyViolation(f"{risk.value} risk cannot auto-finalize without human review")
        if experimental:
            raise PolicyViolation("experimental policy cannot auto-approve")

    # --- AutoMergePolicy ---
    def can_auto_merge(self) -> bool:
        return self.defaults.auto_merge

    # --- NetworkPolicy ---
    def network_allowed(self, task_requires_network: bool = False, *, trace_id=None) -> bool:
        allowed = self.defaults.allow_network or task_requires_network
        if task_requires_network and not self.defaults.allow_network:
            self.audit.record("network_enablement", detail={"reason": "task required"},
                              trace_id=trace_id)
        return allowed

    # --- BudgetPolicy ---
    def check_budget(self, cost_usd: float, *, trace_id=None) -> None:
        if cost_usd > self.defaults.max_cost_usd:
            raise PolicyViolation(
                f"cost {cost_usd} exceeds budget {self.defaults.max_cost_usd}"
            )

    # --- override (always audited) ---
    def override(self, what: str, *, actor: str, reason: str, trace_id=None) -> AuditEvent:
        return self.audit.record(
            "policy_override", actor=actor, target=what, detail={"reason": reason},
            trace_id=trace_id,
        )

    def approve(self, *, actor: str, target: str, trace_id=None) -> AuditEvent:
        return self.audit.record("human_approval", actor=actor, target=target, trace_id=trace_id)
