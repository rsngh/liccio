"""Harness evolution guarded-PR tests (GOALS Alpha 44 P7)."""

from __future__ import annotations

from acp.training.harness_evolution_v2 import (
    cluster_failures,
    evaluate_proposal,
    propose_patch,
)


def _cells():
    out = []
    for i in range(4):
        out.append({"policy": "grep_router", "task_type": "security_fix", "task": f"sec_{i}",
                    "conclusive": True, "solved": False})
    for i in range(3):
        out.append({"policy": "cheap_single", "task_type": "cross_file", "task": f"xf_{i}",
                    "conclusive": True, "solved": False})
    out.append({"policy": "grep_router", "task_type": "bugfix", "task": "ok",
                "conclusive": True, "solved": True})  # success, not clustered
    return out


def test_clusters_real_failures_only() -> None:
    clusters = cluster_failures(_cells(), min_size=2)
    modes = {c.mode for c in clusters}
    assert "grep_router:security_fix" in modes
    assert clusters[0].n == 4   # the biggest cluster first


def test_proposal_has_diff_rationale_and_rollback() -> None:
    c = cluster_failures(_cells())[0]
    p = propose_patch(c)
    assert p.component and p.rationale and p.diff_summary
    assert p.rollback.get("action") == "revert component"


def test_promoted_only_with_lift_and_no_negative_transfer() -> None:
    p = propose_patch(cluster_failures(_cells())[0])
    good = evaluate_proposal(p, static_ok=True, regression_ok=True, negative_transfer=False,
                             canary_lift=0.12)
    assert good.promoted and not good.to_dict()["protected_branch_write"]


def test_rejected_for_negative_transfer() -> None:
    p = propose_patch(cluster_failures(_cells())[0])
    r = evaluate_proposal(p, static_ok=True, regression_ok=True, negative_transfer=True,
                          canary_lift=0.20)
    assert not r.promoted and "negative transfer" in r.decision


def test_rejected_for_no_lift() -> None:
    p = propose_patch(cluster_failures(_cells())[0])
    r = evaluate_proposal(p, static_ok=True, regression_ok=True, negative_transfer=False,
                          canary_lift=0.01)
    assert not r.promoted and "canary lift" in r.decision


def test_rejected_for_failed_security_scan() -> None:
    p = propose_patch(cluster_failures(_cells())[0])
    r = evaluate_proposal(p, static_ok=False, regression_ok=True, negative_transfer=False,
                          canary_lift=0.5)
    assert not r.promoted and "scan" in r.decision
