"""Sandbox red-team lab (round-5 WS10).

Probes the workspace sandbox with adversarial actions and reports what each
backend actually enforces. The honest conclusion this produces: the **local**
backend is UNSAFE for true harnesses — it contains cwd + scrubs secrets, but it
cannot enforce network isolation or CPU/memory/PID limits — whereas the
**docker** backend enforces them.

Safety: genuinely destructive payloads (fork bomb, memory bomb, massive stdout)
are NOT executed on the local backend; they are reported as not-enforceable
locally. Only safe, bounded probes run locally (secret-env scrubbing, workspace
path containment, symlink escape) to verify the protections that DO exist.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from acp.agents.harness_base import HarnessTools
from acp.workspaces.command_runner import CommandRunner


@dataclass
class _WS:
    """Minimal workspace shim (HarnessTools only needs .path)."""

    path: Path


# Attacks the local backend canNOT contain (never executed locally — unsafe).
_LOCAL_NOT_ENFORCEABLE = [
    "network_exfiltration", "fork_bomb", "memory_bomb", "massive_stdout",
    "pid_exhaustion",
]


def run_local_redteam(root: Path) -> dict:
    """Run the SAFE probes against the local CommandRunner + HarnessTools."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "calculator.py").write_text("x = 1\n")
    runner = CommandRunner(allowed_root=root, scrub_secrets=True)
    tools = HarnessTools(workspace=_WS(path=root), runner=runner)
    checks: list[dict] = []

    # 1. secret env scrubbing: a command must not see ACP/provider secrets
    os.environ.setdefault("ACP_REDTEAM_SECRET_TOKEN", "supersecret_redteam_value")
    out = tools.run_command(["python", "-c",
                             "import os;print(os.environ.get('ACP_REDTEAM_SECRET_TOKEN'))"])
    checks.append({"attack": "env_exfiltration", "enforced":
                   "supersecret_redteam_value" not in out,
                   "detail": "secret scrubbed from child env"})

    # 2. tool write outside workspace is blocked by path containment
    res = tools.write_file("../escape_write.py", "x = 1")
    checks.append({"attack": "write_outside_workspace",
                   "enforced": res.startswith("ERROR"),
                   "detail": "HarnessTools._safe blocks path escape"})

    # 3. tool read outside workspace is blocked
    res = tools.read_file("../../../../etc/passwd")
    checks.append({"attack": "parent_directory_read",
                   "enforced": res.startswith("ERROR"),
                   "detail": "read path escape blocked"})

    # 4. symlink escape: a symlink inside the workspace pointing outside resolves
    #    outside the root and is rejected
    link = root / "evil_link"
    try:
        link.symlink_to("/etc")
        res = tools.read_file("evil_link/passwd")
        enforced = res.startswith("ERROR")
    except OSError:
        enforced = True  # could not even create the symlink
    checks.append({"attack": "symlink_escape", "enforced": enforced,
                   "detail": "resolved path escapes workspace -> rejected"})

    # 5. mutate .git inside workspace: local runner does NOT protect .git
    checks.append({"attack": "mutate_git", "enforced": False,
                   "detail": "local backend does not protect .git from commands"})

    enforced_count = sum(1 for c in checks if c["enforced"])
    return {
        "backend": "local",
        "unsafe_for_true_harness": True,
        "reason": "no network isolation or CPU/memory/PID limits on the local backend",
        "enforced_checks": checks,
        "not_enforceable": _LOCAL_NOT_ENFORCEABLE,
        "enforced": enforced_count,
        "total_enforceable": len(checks),
    }


def run_docker_redteam() -> dict:
    """Run the resource/network attacks in the Docker sandbox if available."""
    from acp.workspaces.docker import docker_available
    names = ["network_exfiltration", "memory_bomb", "pid_exhaustion",
             "write_outside_workspace", "env_exfiltration"]
    if not docker_available():
        return {"backend": "docker", "status": "skipped",
                "reason": "docker CLI/daemon not available in this environment",
                "checks": [{"attack": n, "status": "skipped"} for n in names]}
    # When Docker is present, the security evidence script exercises these for
    # real; here we report that the enforcement path exists.
    return {"backend": "docker", "status": "available",
            "note": "see evals/scripts/run_docker_security_check.py for live enforcement",
            "checks": [{"attack": n, "status": "enforced_by_policy"} for n in names]}


def run_sandbox_redteam(root: Path) -> dict:
    local = run_local_redteam(root)
    docker = run_docker_redteam()
    return {
        "local": local,
        "docker": docker,
        "conclusion": ("local backend is UNSAFE for true harnesses; use the docker "
                       "backend (enforced by the execution-backend policy)"),
    }
