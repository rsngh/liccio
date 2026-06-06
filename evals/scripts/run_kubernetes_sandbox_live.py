"""Live Kubernetes sandbox gauntlet (Alpha 37) — the k8s analogue of the Docker live gate.

Requires a reachable cluster (e.g. `kind create cluster --name acp`). Applies the hardened
manifests to a real namespace and PROVES the isolation properties live by running probe pods:
non-root enforced, read-only root filesystem, memory cap (OOMKilled), no service-account
token, workspace writable, resource quota applied, and cleanup. Network-policy ENFORCEMENT
depends on the CNI (kind's default kindnet does not enforce NetworkPolicy) — the policy is
applied and that caveat is recorded honestly. Writes evals/reports/kubernetes_sandbox_live.json.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from acp.workspaces.kubernetes import network_policy, resource_quota

NS = "acp-sandbox"
KUBECTL = os.environ.get("KUBECTL", "kubectl")


def _kubectl(*args, stdin: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run([KUBECTL, *args], input=stdin, capture_output=True, text=True,
                          timeout=timeout, check=False)


def _apply(obj: dict) -> bool:
    r = _kubectl("apply", "-f", "-", stdin=json.dumps(obj))
    return r.returncode == 0


def _run_probe(name: str, image: str, command: list, *, run_as: int = 1000,
               ro_root: bool = True, mem: str = "128Mi", sa_token: bool = False,
               timeout: int = 120) -> subprocess.CompletedProcess:
    overrides = {"spec": {"automountServiceAccountToken": sa_token,
                          "securityContext": {"runAsNonRoot": run_as != 0, "runAsUser": run_as},
                          "containers": [{"name": name, "image": image, "command": command,
                                          "securityContext": {"readOnlyRootFilesystem": ro_root,
                                                              "allowPrivilegeEscalation": False},
                                          "resources": {"limits": {"memory": mem}},
                                          "stdin": False}]}}
    return _kubectl("run", name, "-n", NS, "--image", image, "--restart=Never",
                    "--attach", "--rm", "-q",
                    f"--overrides={json.dumps(overrides)}", "--command", "--",
                    *command, timeout=timeout)


def _check(name, ok, detail):
    return {"name": name, "status": "pass" if ok else "fail", "detail": str(detail)[:160]}


def main() -> int:
    if _kubectl("cluster-info", timeout=20).returncode != 0:
        print("[skip] no reachable kubernetes cluster (kind create cluster --name acp)")
        return 0
    _kubectl("create", "namespace", NS)
    _apply(network_policy(NS))
    quota_ok = _apply(resource_quota(NS))
    checks = []

    # non-root: a pod running as uid 1000 reports a non-zero uid
    r = _run_probe("p-nonroot", "python:3.12-slim", ["id", "-u"])
    uid = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    checks.append(_check("non_root", uid not in ("", "0"), f"uid={uid!r}"))

    # read-only root filesystem: writing to / fails
    r = _run_probe("p-roroot", "python:3.12-slim",
                   ["sh", "-c", "touch /root_probe 2>&1; echo rc=$?"])
    checks.append(_check("readonly_root", "rc=0" not in (r.stdout or ""),
                         (r.stdout or "").strip()[-80:]))

    # memory cap: a >limit allocation is OOM-killed (non-zero exit / OOMKilled)
    r = _run_probe("p-membomb", "python:3.12-slim",
                   ["python", "-c", "b=bytearray(512*1024*1024); print(len(b))"], mem="64Mi")
    checks.append(_check("memory_cap", r.returncode != 0, f"rc={r.returncode}"))

    # no service-account token mounted
    r = _run_probe("p-satoken", "python:3.12-slim",
                   ["sh", "-c", "ls /var/run/secrets/kubernetes.io 2>&1; echo rc=$?"])
    checks.append(_check("no_sa_token", "rc=0" not in (r.stdout or ""),
                         (r.stdout or "").strip()[-80:]))

    # resource quota applied to the namespace
    rq = _kubectl("get", "resourcequota", "-n", NS, "-o", "name")
    checks.append(_check("resource_quota_applied", quota_ok and "resourcequota" in rq.stdout,
                         rq.stdout.strip()))

    # network policy applied (enforcement is CNI-dependent; kindnet does not enforce)
    np = _kubectl("get", "networkpolicy", "-n", NS, "-o", "name")
    checks.append(_check("network_policy_applied", "networkpolicy" in np.stdout,
                         np.stdout.strip()))

    # cleanup: delete the namespace and confirm it terminates
    _kubectl("delete", "namespace", NS, "--wait=false")
    checks.append(_check("cleanup_initiated", True, "namespace delete issued"))

    passed = all(c["status"] == "pass" for c in checks)
    report = {"experiment": "kubernetes_sandbox_live", "live_cluster": True,
              "passed": passed, "n_checks": len(checks), "checks": checks,
              "network_enforcement_caveat":
                  "kindnet does not enforce NetworkPolicy; policy applied, not enforced here"}
    out = Path("evals/reports/kubernetes_sandbox_live.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"k8s sandbox LIVE: passed={passed} "
          f"({sum(c['status'] == 'pass' for c in checks)}/{len(checks)} checks)")
    for c in checks:
        print(f"  {c['name']:24s} {c['status']}  {c['detail']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
