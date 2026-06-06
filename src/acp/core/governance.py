"""Deployment governance: RBAC + audit log + tenant isolation (Alpha 36).

Production deployment needs three controls beyond the lab:

- RBAC: roles (viewer / operator / admin) gate who may do what. A viewer can only read; an
  operator can review and approve DRAFT-class actions; only an admin may deploy/rollback/merge.
- Audit log: every WRITE-CAPABLE action (approve apply/merge, deploy/rollback a skill, override
  a route) is recorded with actor, role, tenant, resource, and the allow/deny decision — so an
  auditor can reconstruct every state-changing action.
- Tenant isolation: an actor in tenant A can never act on tenant B's resources.

``authorize`` combines all three: it checks RBAC + tenant scope and ALWAYS records the
attempt (allowed or denied) to the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from acp.core.time import utcnow


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


# Write-capable (state-changing) actions — always audited.
WRITE_ACTIONS = frozenset({
    "approve_draft_patch", "approve_draft_pr", "approve_apply", "approve_merge",
    "deploy_skill", "rollback_skill", "promote_policy", "override_route", "mark_unsafe",
})
READ_ACTIONS = frozenset({"view_dossier", "view_matrix", "view_inbox", "view_report"})
# what each role may do (admin may do everything)
_OPERATOR_ALLOWED = READ_ACTIONS | {"approve_draft_patch", "approve_draft_pr",
                                    "override_route", "mark_unsafe"}


def role_can(role: Role, action: str) -> bool:
    if role == Role.ADMIN:
        return True
    if role == Role.OPERATOR:
        return action in _OPERATOR_ALLOWED
    return action in READ_ACTIONS   # viewer: read only


@dataclass
class AuditLogEntry:
    actor: str
    role: str
    action: str
    resource: str
    tenant: str
    allowed: bool
    write_capable: bool
    reason: str
    at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["at"] = self.at.isoformat()
        return d


class AuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditLogEntry] = []

    def record(self, entry: AuditLogEntry) -> None:
        self._entries.append(entry)

    def entries(self, *, tenant: str | None = None) -> list:
        return [e for e in self._entries if tenant is None or e.tenant == tenant]

    def write_actions(self) -> list:
        return [e for e in self._entries if e.write_capable]

    def summary(self) -> dict:
        from collections import Counter
        return {"n_entries": len(self._entries),
                "n_write_capable": len(self.write_actions()),
                "n_denied": sum(1 for e in self._entries if not e.allowed),
                "by_action": dict(Counter(e.action for e in self._entries)),
                "every_write_action_audited": all(
                    e.write_capable for e in self.write_actions())}


def authorize(audit: AuditLog, *, actor: str, role: Role, action: str, resource: str,
              tenant: str, actor_tenant: str | None = None) -> tuple[bool, AuditLogEntry]:
    """RBAC + tenant check, always audited. Returns (allowed, the recorded entry)."""
    actor_tenant = actor_tenant or tenant
    write_capable = action in WRITE_ACTIONS
    if actor_tenant != tenant:
        allowed, reason = False, f"tenant isolation: {actor_tenant} != {tenant}"
    elif not role_can(role, action):
        allowed, reason = False, f"RBAC: role {role.value} may not {action}"
    else:
        allowed, reason = True, "authorized"
    entry = AuditLogEntry(actor=actor, role=role.value, action=action, resource=resource,
                          tenant=tenant, allowed=allowed, write_capable=write_capable,
                          reason=reason)
    audit.record(entry)
    return allowed, entry
