"""Live Docker security evidence pack (round-4 Block D).

Runs a sandbox container through the same DockerWorkspaceManager the control
plane uses and asserts the security invariants that make a true harness safe to
run: non-root, no network, memory/pid caps, workspace containment, cleanup.

Produces evals/reports/docker_security.{json,md}. If Docker is unavailable the
report is written with an EXPLICIT skipped status (every check skipped + reason)
so the artifact is never silently empty.

Usage:
    uv run python evals/scripts/run_docker_security_check.py
"""

from __future__ import annotations

import json
import subprocess  # noqa: S404 - host-side docker invocation, argv list, no shell
import tempfile
import uuid
from pathlib import Path
from typing import Any

from git import Repo

from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.workspace import WorkspacePolicy
from acp.workspaces.docker import DockerWorkspaceManager, docker_available

REPORT_DIR = Path("evals/reports")


def _run(argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - argv list, no shell
        argv, capture_output=True, text=True, timeout=timeout, check=False)


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "detail": detail[:500]}


def run_checks() -> dict[str, Any]:
    if not docker_available():
        names = ["pwd_is_workspace", "non_root", "network_blocked", "memory_hog_fails",
                 "pid_limit", "workspace_write_reflected", "cleanup_removes_worktree"]
        return {
            "docker_available": False,
            "status": "skipped",
            "reason": "docker CLI/daemon not available in this environment",
            "checks": [{"name": n, "status": "skipped",
                        "detail": "docker unavailable"} for n in names],
        }

    tmp = Path(tempfile.mkdtemp(prefix="acp_docker_sec_"))
    src = tmp / "repo"
    src.mkdir()
    (src / "marker.txt").write_text("base\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["marker.txt"])
    repo.index.commit("init")

    mgr = DockerWorkspaceManager(tmp / "ws", memory_mb=256, pids_limit=64)
    r = Repository(name="sec", local_path=str(src), default_branch="master")
    snap = RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha)
    ws = mgr.create(r, snap, WorkspacePolicy(backend="docker", allow_network=False,
                                             memory_mb=256, pids_limit=64,
                                             run_as_nonroot=True))
    checks: list[dict[str, Any]] = []
    try:
        # 1. pwd == /workspace
        p = _run(mgr.docker_run_argv(ws, ["pwd"]))
        checks.append(_check("pwd_is_workspace", p.stdout.strip() == "/workspace",
                             f"pwd={p.stdout.strip()!r}"))

        # 2. non-root (uid != 0)
        p = _run(mgr.docker_run_argv(ws, ["id", "-u"]))
        checks.append(_check("non_root", p.stdout.strip() not in ("", "0"),
                             f"uid={p.stdout.strip()!r}"))

        # 3. network none blocks outbound connections
        net = ["python", "-c",
               "import urllib.request,sys;\n"
               "try:\n urllib.request.urlopen('http://example.com',timeout=5);"
               "print('REACHED')\nexcept Exception as e:\n print('BLOCKED',type(e).__name__)"]
        p = _run(mgr.docker_run_argv(ws, net))
        checks.append(_check("network_blocked", "REACHED" not in p.stdout,
                             f"out={p.stdout.strip()[:120]!r}"))

        # 4. memory hog is killed / fails (allocate ~1GB under a 256MB cap)
        hog = ["python", "-c", "b=bytearray(1024*1024*1024); print(len(b))"]
        p = _run(mgr.docker_run_argv(ws, hog))
        checks.append(_check("memory_hog_fails", p.returncode != 0,
                             f"rc={p.returncode}"))

        # 5. pid limit enforced (spawning > limit threads should error)
        pid = ["python", "-c",
               "import threading,time\n"
               "def f():\n time.sleep(30)\n"
               "n=0\n"
               "try:\n"
               " while n<500:\n  threading.Thread(target=f,daemon=True).start();n+=1\n"
               " print('SPAWNED',n)\n"
               "except Exception as e:\n print('LIMITED',n,type(e).__name__)"]
        p = _run(mgr.docker_run_argv(ws, pid))
        checks.append(_check("pid_limit", "SPAWNED 500" not in p.stdout,
                             f"out={p.stdout.strip()[:120]!r} rc={p.returncode}"))

        # 6. a file written in /workspace is reflected on the host bind mount
        token = uuid.uuid4().hex
        p = _run(mgr.docker_run_argv(ws, ["sh", "-c", f"echo {token} > /workspace/out.txt"]))
        host_file = Path(ws.path) / "out.txt"
        reflected = host_file.exists() and token in host_file.read_text()
        checks.append(_check("workspace_write_reflected", reflected,
                             f"host_file_exists={host_file.exists()}"))

        # 7. cleanup removes the worktree
        ws_path = Path(ws.path)
        mgr.cleanup(ws, succeeded=True)
        checks.append(_check("cleanup_removes_worktree", not ws_path.exists(),
                             f"still_exists={ws_path.exists()}"))
    except Exception as exc:  # noqa: BLE001 - record, never crash the evidence run
        checks.append(_check("harness_error", False, f"{type(exc).__name__}: {exc}"))

    passed = sum(1 for c in checks if c["status"] == "pass")
    return {
        "docker_available": True,
        "status": "pass" if passed == len(checks) else "fail",
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = ["# Docker security evidence", "",
             f"- docker available: {report['docker_available']}",
             f"- status: **{report['status']}**"]
    if report["status"] == "skipped":
        lines.append(f"- reason: {report['reason']}")
    else:
        lines.append(f"- passed: {report.get('passed')}/{report.get('total')}")
    lines += ["", "| check | status | detail |", "| --- | --- | --- |"]
    for c in report["checks"]:
        lines.append(f"| {c['name']} | {c['status']} | {c['detail']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    report = run_checks()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "docker_security.json").write_text(json.dumps(report, indent=2))
    (REPORT_DIR / "docker_security.md").write_text(to_markdown(report))
    print(f"docker_security: status={report['status']} "
          f"({report.get('passed', 0)}/{report.get('total', len(report['checks']))})")
    # An explicit skip is a successful run of the evidence script.
    return 0 if report["status"] in ("pass", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
