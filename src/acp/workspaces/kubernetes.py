"""Kubernetes workspace manager + sandbox manifests/validation (charter §9, Alpha 37).

Production should not depend on a fragile local Docker daemon. This generates the Kubernetes
objects a hardened ACP sandbox pod needs (Pod with a security profile, deny-all NetworkPolicy,
ResourceQuota) and STATICALLY validates the same properties the Docker live-security gate
enforces. No live cluster is available here, so ``create`` still raises (honest) and the
SandboxHealthReport reflects manifest validation, not live pod execution.
"""

from __future__ import annotations

from pathlib import Path

from acp.core.errors import AdapterUnavailable
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy
from acp.workspaces.base import Workspace

SANDBOX_NAMESPACE = "acp-sandbox"
CHECK_NAMES = ("non_root", "no_network", "memory_cap", "cpu_cap", "pid_cap",
               "workspace_only_mount", "secret_isolation", "no_sa_token", "auto_cleanup")


def pod_manifest(*, name: str, image: str, command: list, memory_mb: int = 256,
                 cpu: str = "500m", pids: int = 64,
                 namespace: str = SANDBOX_NAMESPACE) -> dict:
    """A hardened sandbox Pod spec (non-root, capped, no network, workspace-only, ephemeral)."""
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": name, "namespace": namespace,
                     "labels": {"app": "acp-sandbox", "acp.managed": "true"}},
        "spec": {
            "restartPolicy": "Never",
            "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "runAsUser": 1000,
                                "runAsGroup": 1000, "fsGroup": 1000},
            "containers": [{
                "name": "task", "image": image, "command": command,
                "securityContext": {"allowPrivilegeEscalation": False, "runAsNonRoot": True,
                                    "runAsUser": 1000, "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]}},
                "resources": {"limits": {"memory": f"{memory_mb}Mi", "cpu": cpu,
                                         "pids": str(pids)}},
                "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"}],
                "env": [],
            }],
            "volumes": [{"name": "workspace", "emptyDir": {}}],
        },
    }


def network_policy(namespace: str = SANDBOX_NAMESPACE) -> dict:
    """Deny-all egress/ingress for the sandbox namespace (no default network)."""
    return {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": "acp-deny-all", "namespace": namespace},
            "spec": {"podSelector": {"matchLabels": {"app": "acp-sandbox"}},
                     "policyTypes": ["Ingress", "Egress"], "ingress": [], "egress": []}}


def resource_quota(namespace: str = SANDBOX_NAMESPACE) -> dict:
    return {"apiVersion": "v1", "kind": "ResourceQuota",
            "metadata": {"name": "acp-sandbox-quota", "namespace": namespace},
            "spec": {"hard": {"pods": "16", "limits.cpu": "8", "limits.memory": "8Gi"}}}


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def validate_pod_security(manifest: dict, *, netpol: dict | None = None) -> dict:
    """Static security validation: the same properties the Docker live gate enforces."""
    spec = manifest.get("spec", {})
    c = (spec.get("containers") or [{}])[0]
    csc = c.get("securityContext", {})
    limits = c.get("resources", {}).get("limits", {})
    np = netpol or network_policy(manifest.get("metadata", {}).get("namespace",
                                                                   SANDBOX_NAMESPACE))
    checks = [
        _check("non_root", bool(csc.get("runAsNonRoot")) and csc.get("runAsUser", 0) != 0,
               f"runAsUser={csc.get('runAsUser')}"),
        _check("no_network", np.get("spec", {}).get("egress") == []
               and "Egress" in np.get("spec", {}).get("policyTypes", []),
               "deny-all egress NetworkPolicy"),
        _check("memory_cap", "memory" in limits, f"memory={limits.get('memory')}"),
        _check("cpu_cap", "cpu" in limits, f"cpu={limits.get('cpu')}"),
        _check("pid_cap", "pids" in limits, f"pids={limits.get('pids')}"),
        _check("workspace_only_mount",
               [m.get("mountPath") for m in c.get("volumeMounts", [])] == ["/workspace"]
               and csc.get("readOnlyRootFilesystem") is True, "workspace-only + RO root"),
        _check("secret_isolation", c.get("env") == [], "no secret env injected"),
        _check("no_sa_token", spec.get("automountServiceAccountToken") is False,
               "service-account token not mounted"),
        _check("auto_cleanup", spec.get("restartPolicy") == "Never", "ephemeral pod"),
    ]
    passed = all(ch["status"] == "pass" for ch in checks)
    return {"experiment": "kubernetes_sandbox_health", "passed": passed,
            "live_cluster": False, "checks": checks,
            "note": "static manifest validation (no live cluster in this environment)"}


class KubernetesWorkspaceManager:
    backend = "kubernetes"

    def __init__(self, root: Path | str, namespace: str = SANDBOX_NAMESPACE) -> None:
        self.root = Path(root)
        self.namespace = namespace

    def sandbox_manifests(self, *, name: str, image: str, command: list,
                          memory_mb: int = 256, pids: int = 64) -> dict:
        """All hardened objects for one sandbox run (pod + netpol + quota)."""
        return {"pod": pod_manifest(name=name, image=image, command=command,
                                    memory_mb=memory_mb, pids=pids, namespace=self.namespace),
                "network_policy": network_policy(self.namespace),
                "resource_quota": resource_quota(self.namespace)}

    def sandbox_health(self, *, name: str = "probe", image: str = "python:3.12-slim",
                       command: list | None = None) -> dict:
        m = self.sandbox_manifests(name=name, image=image, command=command or ["true"])
        return validate_pod_security(m["pod"], netpol=m["network_policy"])

    def create(
        self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy
    ) -> Workspace:
        raise AdapterUnavailable("kubernetes workspace backend is not configured (no cluster)")

    def cleanup(self, workspace: Workspace) -> None:
        return None
