"""Deployment governance: RBAC + audit log + tenant isolation (Alpha 36)."""

from __future__ import annotations

from acp.core.governance import AuditLog, Role, authorize, role_can


def test_rbac_role_permissions() -> None:
    assert role_can(Role.ADMIN, "deploy_skill")
    assert not role_can(Role.OPERATOR, "deploy_skill")      # operators can't deploy
    assert role_can(Role.OPERATOR, "approve_draft_pr")
    assert not role_can(Role.VIEWER, "approve_draft_pr")    # viewers read-only
    assert role_can(Role.VIEWER, "view_dossier")


def test_admin_can_deploy_and_is_audited() -> None:
    log = AuditLog()
    ok, entry = authorize(log, actor="alice", role=Role.ADMIN, action="deploy_skill",
                          resource="skill:verify", tenant="acme")
    assert ok and entry.write_capable and entry.allowed
    assert len(log.write_actions()) == 1


def test_operator_denied_deploy_still_audited() -> None:
    log = AuditLog()
    ok, entry = authorize(log, actor="bob", role=Role.OPERATOR, action="deploy_skill",
                          resource="skill:x", tenant="acme")
    assert not ok and not entry.allowed and "RBAC" in entry.reason
    assert log.summary()["n_denied"] == 1   # denial is recorded


def test_tenant_isolation_blocks_cross_tenant() -> None:
    log = AuditLog()
    ok, entry = authorize(log, actor="eve", role=Role.ADMIN, action="rollback_skill",
                          resource="skill:y", tenant="acme", actor_tenant="other")
    assert not ok and "tenant isolation" in entry.reason


def test_every_write_action_is_audited() -> None:
    log = AuditLog()
    authorize(log, actor="a", role=Role.ADMIN, action="approve_merge", resource="pr:1",
              tenant="t")
    authorize(log, actor="a", role=Role.VIEWER, action="view_matrix", resource="m", tenant="t")
    s = log.summary()
    assert s["n_entries"] == 2 and s["n_write_capable"] == 1
    assert s["every_write_action_audited"]


def test_audit_log_tenant_scoped_query() -> None:
    log = AuditLog()
    authorize(log, actor="a", role=Role.ADMIN, action="deploy_skill", resource="x", tenant="t1")
    authorize(log, actor="b", role=Role.ADMIN, action="deploy_skill", resource="y", tenant="t2")
    assert len(log.entries(tenant="t1")) == 1 and len(log.entries()) == 2
