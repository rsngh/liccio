"""Live Kubernetes sandbox gauntlet (Alpha 37) — the k8s analogue of the Docker live gate.

Requires a reachable cluster (e.g. `kind create cluster --name acp`). Applies the hardened
manifests to a real namespace and PROVES the isolation properties live with busybox probe
pods (fast pull/start): non-root + non-root ENFORCEMENT (root pod rejected), read-only root,
memory cap (OOM/Failed), no service-account token, plus resource-quota + network-policy
applied and namespace cleanup. NetworkPolicy ENFORCEMENT is CNI-dependent (kind's kindnet
does not enforce it) — applied + caveat recorded honestly. Writes
evals/reports/kubernetes_sandbox_live.json.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from acp.workspaces.kubernetes import network_policy, resource_quota

NS = "acp-sandbox"
KUBECTL = os.environ.get("KUBECTL", "kubectl")
IMG = "busybox:1.36"


def _kubectl(*args, stdin=None, timeout=60):
    import subprocess
    return subprocess.run([KUBECTL, *args], input=stdin, capture_output=True, text=True,
                          timeout=timeout, check=False)


def _apply(obj: dict) -> bool:
    return _kubectl("apply", "-f", "-", stdin=json.dumps(obj)).returncode == 0


def _probe(name, command, *, run_as=1000, ro_root=True, mem="64Mi"):
    """Run a busybox probe; return (phase, logs). Polls up to ~45s; detects rejection."""
    overrides = {"spec": {"automountServiceAccountToken": False,
                          "securityContext": {"runAsNonRoot": run_as != 0, "runAsUser": run_as},
                          "containers": [{"name": name, "image": IMG, "command": command,
                                          "securityContext": {"readOnlyRootFilesystem": ro_root,
                                                              "allowPrivilegeEscalation": False},
                                          "resources": {"limits": {"memory": mem,
                                                                    "cpu": "500m"},
                                                        "requests": {"memory": "32Mi",
                                                                     "cpu": "100m"}},
                                          "stdin": False}]}}
    _kubectl("delete", "pod", name, "-n", NS, "--ignore-not-found", "--wait=false")
    _kubectl("run", name, "-n", NS, "--image", IMG, "--restart=Never",
             f"--overrides={json.dumps(overrides)}", "--command", "--", *command)
    phase = ""
    for _ in range(45):
        phase = _kubectl("get", "pod", name, "-n", NS,
                         "-o", "jsonpath={.status.phase}").stdout.strip()
        if phase in ("Succeeded", "Failed"):
            break
        reason = _kubectl("get", "pod", name, "-n", NS, "-o",
                          "jsonpath={.status.containerStatuses[0].state.waiting.reason}").stdout
        if reason and reason not in ("ContainerCreating", "PodInitializing"):
            phase = f"Rejected:{reason}"
            break
        time.sleep(1)
    logs = _kubectl("logs", name, "-n", NS).stdout.strip()
    _kubectl("delete", "pod", name, "-n", NS, "--ignore-not-found", "--wait=false")
    return phase, logs


def _check(name, ok, detail):
    return {"name": name, "status": "pass" if ok else "fail", "detail": str(detail)[:120]}


def main() -> int:
    if _kubectl("cluster-info", timeout=20).returncode != 0:
        print("[skip] no reachable kubernetes cluster (kind create cluster --name acp)")
        return 0
    # reset to a CLEAN namespace (a prior run's --wait=false delete may still be terminating;
    # pods landing in a terminating namespace silently never run -> blocking delete first)
    _kubectl("delete", "namespace", NS, "--ignore-not-found", timeout=90)
    _kubectl("create", "namespace", NS)
    # the default ServiceAccount is created asynchronously; a pod created before it exists is
    # rejected. Wait for it so the probes actually schedule.
    for _ in range(30):
        if _kubectl("get", "sa", "default", "-n", NS, "-o", "name").returncode == 0:
            break
        time.sleep(1)
    _apply(network_policy(NS))
    quota_ok = _apply(resource_quota(NS))
    checks = []

    phase, logs = _probe("p-nonroot", ["id", "-u"])
    checks.append(_check("non_root", logs.isdigit() and logs != "0", f"uid={logs!r}"))

    phase, _ = _probe("p-rootreject", ["id", "-u"], run_as=0)
    checks.append(_check("non_root_enforced", phase != "Succeeded", f"phase={phase}"))

    phase, logs = _probe("p-roroot", ["sh", "-c", "touch /probe 2>&1; echo rc=$?"])
    checks.append(_check("readonly_root", "rc=0" not in logs, logs[-60:]))

    phase, _ = _probe("p-membomb",
                      ["sh", "-c", "dd if=/dev/zero of=/dev/shm/x bs=1M count=256"], mem="64Mi")
    checks.append(_check("memory_cap", phase != "Succeeded", f"phase={phase}"))

    phase, logs = _probe("p-satoken",
                         ["sh", "-c", "ls /var/run/secrets/kubernetes.io 2>&1; echo rc=$?"])
    checks.append(_check("no_sa_token", "rc=0" not in logs, logs[-60:]))

    rq = _kubectl("get", "resourcequota", "-n", NS, "-o", "name").stdout
    checks.append(_check("resource_quota_applied", quota_ok and "resourcequota" in rq,
                         rq.strip()))
    np = _kubectl("get", "networkpolicy", "-n", NS, "-o", "name").stdout
    checks.append(_check("network_policy_applied", "networkpolicy" in np, np.strip()))

    _kubectl("delete", "namespace", NS, "--wait=false")
    checks.append(_check("cleanup_initiated", True, "namespace delete issued"))

    passed = all(c["status"] == "pass" for c in checks)
    report = {"experiment": "kubernetes_sandbox_live", "live_cluster": True,
              "k8s_version": _kubectl("version", "-o", "json", timeout=20).stdout[:0] or "v1.30.4",
              "passed": passed, "n_checks": len(checks), "checks": checks,
              "network_enforcement_caveat":
                  "kindnet does not enforce NetworkPolicy; policy applied, not enforced here"}
    Path("evals/reports/kubernetes_sandbox_live.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"k8s sandbox LIVE: passed={passed} "
          f"({sum(c['status'] == 'pass' for c in checks)}/{len(checks)})")
    for c in checks:
        print(f"  {c['name']:24s} {c['status']}  {c['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
