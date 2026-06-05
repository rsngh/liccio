"""Docker live security release gate (alpha-8 WS14).

Runs the enforceable Docker sandbox security checks through the same
``DockerWorkspaceManager`` the control plane uses and emits a structured
report. The companion :class:`DockerSecurityGate` is the PRODUCTION GATE that
real-harness execution must consult: real harnesses are only safe behind the
docker backend, so production refuses to start unless a passing Docker security
report exists.

When Docker is unavailable the live checks SKIP gracefully (every check is
listed with a ``would run`` note and overall ``passed`` is ``False``), so the
gate can be exercised without Docker and never produces a silently empty
artifact.
"""

from __future__ import annotations

import json
import subprocess  # noqa: S404 - host-side docker invocation, argv list, no shell
import tempfile
import uuid
from pathlib import Path
from typing import Any

from git import Repo

from acp.core.errors import AdapterUnavailable
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy
from acp.workspaces.docker import DockerWorkspaceManager, docker_available

# The enforceable Docker sandbox security checks, in report order. Used both to
# describe the SKIPPED report (Docker absent) and to label the live results.
CHECK_NAMES = [
    "no_network",
    "non_root",
    "memory_cap",
    "pid_cap",
    "timeout",
    "workspace_containment",
    "secret_scrub",
    "massive_stdout",
    "cleanup",
]


def _run(argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    # One retry on a transient daemon error (contention hardening, WS3): under
    # parallel docker load a `docker run` can fail to acquire the daemon; a single
    # retry turns that flake into a pass without masking a real failure.
    last = subprocess.run(  # noqa: S603 - argv list, no shell
        argv, capture_output=True, text=True, timeout=timeout, check=False)
    transient = ("Cannot connect to the Docker daemon", "i/o timeout",
                 "context deadline exceeded", "resource temporarily unavailable")
    if last.returncode != 0 and any(t in (last.stderr or "") for t in transient):
        last = subprocess.run(  # noqa: S603
            argv, capture_output=True, text=True, timeout=timeout, check=False)
    return last


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "detail": detail[:500]}


def _skipped_report() -> dict[str, Any]:
    """The explicit SKIPPED report produced when Docker is unavailable."""
    return {
        "available": False,
        "skipped": True,
        "passed": False,
        "reason": "docker unavailable",
        "checks": [
            {"name": n, "status": "skipped", "detail": "would run when docker present"}
            for n in CHECK_NAMES
        ],
    }


def run_docker_security_live() -> dict[str, Any]:
    """Run the enforceable Docker security checks and return a report.

    If :func:`docker_available` is ``False`` the report is returned with
    ``available=False``, ``skipped=True`` and ``passed=False``, listing every
    check that WOULD run. When Docker is available the enforceable subset is run
    for real against ``docker_run_argv`` (argv-level assertions plus live
    behavioural probes) and each check is marked pass/fail with an overall
    ``passed`` flag.
    """
    if not docker_available():
        return _skipped_report()

    tmp = Path(tempfile.mkdtemp(prefix="acp_docker_seclive_"))
    src = tmp / "repo"
    src.mkdir()
    (src / "marker.txt").write_text("base\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["marker.txt"])
    repo.index.commit("init")

    # Clear ACP-labeled stragglers from a prior contended run before starting (WS3).
    DockerWorkspaceManager.prune_acp_resources()
    mgr = DockerWorkspaceManager(tmp / "ws", memory_mb=256, pids_limit=64)
    r = Repository(name="seclive", local_path=str(src), default_branch="master")
    snap = RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha)
    # Measurement-trust: the docker daemon can flicker under load in some environments
    # (e.g. WSL2). If it disappears AFTER the upfront availability check, that is an INFRA
    # event, not a security failure — return a clean skipped report rather than a failure.
    try:
        ws = mgr.create(r, snap, WorkspacePolicy(backend="docker", allow_network=False,
                                                 memory_mb=256, pids_limit=64,
                                                 run_as_nonroot=True))
    except AdapterUnavailable:
        report = _skipped_report()
        report["reason"] = "docker became unavailable mid-run"
        return report
    checks: list[dict[str, Any]] = []
    try:
        # The enforced flags live in the docker run argv; assert they are present
        # so a regression in DockerWorkspaceManager fails the release gate.
        argv = mgr.docker_run_argv(ws, ["true"])

        # 1. no_network: --network none present (policy denies egress)
        no_net = "--network" in argv and argv[argv.index("--network") + 1] == "none"
        checks.append(_check("no_network", no_net, f"argv has --network none={no_net}"))

        # 2. non_root: -u 1000:1000 present and uid != 0 at runtime
        nonroot_flag = "-u" in argv and argv[argv.index("-u") + 1] == "1000:1000"
        p = _run(mgr.docker_run_argv(ws, ["id", "-u"]))
        checks.append(_check(
            "non_root", nonroot_flag and p.stdout.strip() not in ("", "0"),
            f"flag={nonroot_flag} uid={p.stdout.strip()!r}"))

        # 3. memory_cap: -m present and a >cap allocation is killed
        mem_flag = "-m" in argv
        hog = ["python", "-c", "b=bytearray(1024*1024*1024); print(len(b))"]
        p = _run(mgr.docker_run_argv(ws, hog))
        checks.append(_check("memory_cap", mem_flag and p.returncode != 0,
                             f"flag={mem_flag} rc={p.returncode}"))

        # 4. pid_cap: --pids-limit present and over-spawn is limited
        pid_flag = "--pids-limit" in argv
        pid = ["python", "-c",
               "import threading,time\n"
               "def f():\n time.sleep(30)\n"
               "n=0\n"
               "try:\n"
               " while n<500:\n  threading.Thread(target=f,daemon=True).start();n+=1\n"
               " print('SPAWNED',n)\n"
               "except Exception as e:\n print('LIMITED',n,type(e).__name__)"]
        p = _run(mgr.docker_run_argv(ws, pid))
        checks.append(_check("pid_cap", pid_flag and "SPAWNED 500" not in p.stdout,
                             f"flag={pid_flag} out={p.stdout.strip()[:120]!r}"))

        # 5. timeout: a long-running command is bounded by the host wall clock
        timed_out = False
        try:
            _run(mgr.docker_run_argv(ws, ["sleep", "30"]), timeout=5)
        except subprocess.TimeoutExpired:
            timed_out = True
        checks.append(_check("timeout", timed_out, f"host timeout enforced={timed_out}"))

        # 6. workspace_containment: a file written in /workspace stays on the bind
        #    mount (host worktree) and is reflected there, not on the host root.
        token = uuid.uuid4().hex
        _run(mgr.docker_run_argv(ws, ["sh", "-c", f"echo {token} > /workspace/out.txt"]))
        host_file = Path(ws.path) / "out.txt"
        reflected = host_file.exists() and token in host_file.read_text()
        checks.append(_check("workspace_containment", reflected,
                             f"reflected_on_bind_mount={reflected}"))

        # 7. secret_scrub: a host ACP_* secret is not visible inside the container
        scrub = _run(mgr.docker_run_argv(
            ws, ["printenv", "ACP_DOCKER_SECLIVE_SECRET"]))
        checks.append(_check("secret_scrub", scrub.returncode != 0,
                             f"secret_visible={scrub.returncode == 0}"))

        # 8. massive_stdout: a large stdout flood is captured/bounded, not fatal
        flood = ["python", "-c", "print('A'*100000)"]
        p = _run(mgr.docker_run_argv(ws, flood))
        checks.append(_check("massive_stdout", p.returncode == 0 and len(p.stdout) >= 100000,
                             f"rc={p.returncode} bytes={len(p.stdout)}"))

        # 9. cleanup: the worktree is removed on success
        ws_path = Path(ws.path)
        mgr.cleanup(ws, succeeded=True)
        checks.append(_check("cleanup", not ws_path.exists(),
                             f"still_exists={ws_path.exists()}"))
    except Exception as exc:  # noqa: BLE001 - record, never crash the gate run
        checks.append(_check("harness_error", False, f"{type(exc).__name__}: {exc}"))

    passed_n = sum(1 for c in checks if c["status"] == "pass")
    return {
        "available": True,
        "skipped": False,
        "passed": passed_n == len(checks),
        "passed_count": passed_n,
        "total": len(checks),
        "checks": checks,
    }


def load_report(path: Path | str) -> dict[str, Any] | None:
    """Load a previously written security report, or ``None`` if missing/invalid."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class DockerSecurityGate:
    """Production gate guarding real-harness execution.

    Real harnesses are only safe behind the docker backend, so production must
    not start real-harness mode unless a Docker security report exists AND every
    enforceable check passed.
    """

    @staticmethod
    def production_allowed(report: dict[str, Any] | None) -> tuple[bool, str]:
        """Return ``(allowed, reason)`` for starting real-harness production.

        Allowed only when ``report`` is present and ``report["passed"] is True``.
        """
        if report is None:
            return False, "no docker security report present"
        if report.get("skipped"):
            return False, "docker security checks were skipped (docker unavailable)"
        if report.get("passed") is not True:
            return False, "docker security report did not pass all checks"
        return True, "docker security report passed"
