"""Kubernetes sandbox manifests + security validation (Alpha 37)."""

from __future__ import annotations

from acp.workspaces.kubernetes import (
    CHECK_NAMES,
    KubernetesWorkspaceManager,
    network_policy,
    pod_manifest,
    validate_pod_security,
)


def test_hardened_pod_passes_all_security_checks() -> None:
    m = pod_manifest(name="t", image="python:3.12-slim", command=["true"])
    health = validate_pod_security(m)
    assert health["passed"]
    assert [c["name"] for c in health["checks"]] == list(CHECK_NAMES)
    assert all(c["status"] == "pass" for c in health["checks"])
    assert health["live_cluster"] is False   # honest: static validation, no cluster


def test_root_pod_fails_non_root_check() -> None:
    m = pod_manifest(name="t", image="x", command=["true"])
    m["spec"]["containers"][0]["securityContext"]["runAsUser"] = 0
    health = validate_pod_security(m)
    assert not health["passed"]
    nonroot = next(c for c in health["checks"] if c["name"] == "non_root")
    assert nonroot["status"] == "fail"


def test_open_network_fails_no_network_check() -> None:
    m = pod_manifest(name="t", image="x", command=["true"])
    open_np = network_policy()
    open_np["spec"]["egress"] = [{"to": [{}]}]   # allow egress
    health = validate_pod_security(m, netpol=open_np)
    assert next(c for c in health["checks"] if c["name"] == "no_network")["status"] == "fail"


def test_secret_env_fails_isolation() -> None:
    m = pod_manifest(name="t", image="x", command=["true"])
    m["spec"]["containers"][0]["env"] = [{"name": "OPENAI_API_KEY", "value": "sk-x"}]
    health = validate_pod_security(m)
    assert next(c for c in health["checks"]
                if c["name"] == "secret_isolation")["status"] == "fail"


def test_manager_bundles_manifests_and_health() -> None:
    mgr = KubernetesWorkspaceManager("/tmp/k")
    bundle = mgr.sandbox_manifests(name="run1", image="python:3.12-slim", command=["true"])
    assert set(bundle) == {"pod", "network_policy", "resource_quota"}
    assert bundle["pod"]["metadata"]["namespace"] == "acp-sandbox"
    assert mgr.sandbox_health()["passed"]
