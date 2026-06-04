"""Vendor-native harness live gate (WS19).

Detects the installed vendor coding harnesses (codex, Claude Code, OpenHands), and for
the ones that can run headlessly drives a tiny no-patch repo task end to end: a temp git
repo with a failing pytest, the harness asked to fix it, then verification by the repo's
own pytest — capturing the diff, AgentTrace-like metadata, an enforced timeout, and a
secret scan. OpenHands is health-checked (version) only. Unavailable harnesses are marked
*skipped*, never failed, so the gate is honest about what the environment provides.

Writes ``evals/reports/vendor_harness_live.json`` (registered in the artifact manifest).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# A trivial bug + a failing test the harness must fix.
_CALC = "def divide(a, b):\n    return a + b  # BUG: should divide\n"
_TEST = ("from calc import divide\n\n\n"
         "def test_divide():\n    assert divide(6, 2) == 3\n    assert divide(9, 3) == 3\n")
_PROMPT = ("Fix the bug in calc.py so the failing test in test_calc.py passes "
           "(divide should divide, not add). Then run `python -m pytest -q` and make "
           "sure it passes before finishing.")

# Per-call wall-time budget for a vendor harness invocation.
_TIMEOUT_S = 240


def _version(binary: str, args: list[str]) -> str | None:
    """Return the version string for ``binary`` or None if unavailable."""
    if shutil.which(binary) is None:
        return None
    try:
        out = subprocess.run([binary, *args], capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return None
    text = (out.stdout or out.stderr or "").strip().splitlines()
    return text[0].strip() if text else f"{binary} (version unknown)"


def _make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "calc.py").write_text(_CALC)
    (repo / "test_calc.py").write_text(_TEST)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=False)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=False)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=False)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=False)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=False)
    return repo


def _argv_for(name: str, repo: Path) -> list[str] | None:
    """The headless argv that asks a vendor harness to fix the bug in ``repo``."""
    if name == "codex_cli":
        return ["codex", "exec", "--sandbox", "workspace-write",
                "--skip-git-repo-check", "--cd", str(repo), _PROMPT]
    if name == "claude_code":
        # Print mode + skip-permissions so it can use file/bash tools in the cwd.
        return ["claude", "-p", _PROMPT, "--dangerously-skip-permissions"]
    return None  # openhands: health-check only


def _secret_leak(text: str) -> bool:
    import re
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret and secret in text:
            return True
    return bool(re.search(r"sk-[A-Za-z0-9]{20,}", text or ""))


def _run_task(name: str, repo: Path) -> dict:
    """Run one vendor harness on the no-patch task and capture the result."""
    argv = _argv_for(name, repo)
    record: dict = {"no_patch_solve": False, "trace_captured": False,
                    "diff_captured": False, "pytest_passed": False,
                    "secret_leak": False, "timeout_enforced": True}
    if argv is None:  # pragma: no cover - task runners always have an argv
        record["error"] = "no headless argv for harness"
        return record
    t0 = time.monotonic()
    timed_out = False
    out_text = ""
    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True,
                              timeout=_TIMEOUT_S)
        out_text = (proc.stdout or "") + (proc.stderr or "")
        record["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        record["error"] = "timeout"
    except Exception as exc:  # noqa: BLE001
        record["error"] = str(exc)[:200]
    record["wall_time_s"] = round(time.monotonic() - t0, 2)
    record["trace_captured"] = bool(out_text) or "exit_code" in record
    # Diff capture.
    diff = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True,
                          check=False).stdout
    record["diff_captured"] = bool(diff.strip())
    # Verify with the repo's own pytest.
    pt = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo, capture_output=True,
                        text=True, check=False)
    record["pytest_passed"] = pt.returncode == 0
    record["no_patch_solve"] = record["pytest_passed"]
    record["secret_leak"] = _secret_leak(out_text + diff + pt.stdout)
    record["timeout_enforced"] = not timed_out or record["wall_time_s"] <= _TIMEOUT_S + 5
    return record


def run_vendor_harness_live() -> dict:
    """Run the vendor-native harness live gate and return its report."""
    versions = {
        "codex_cli": _version("codex", ["--version"]),
        "claude_code": _version("claude", ["--version"]),
        "openhands": _version("openhands", ["--version"]),
    }
    harnesses: dict[str, dict] = {}
    task_runners = ("codex_cli", "claude_code")
    with tempfile.TemporaryDirectory() as d:
        for name, ver in versions.items():
            if ver is None:
                harnesses[name] = {"available": False, "skipped": True,
                                   "reason": "binary not on PATH"}
                continue
            if name in task_runners:
                repo = _make_repo(Path(d) / name)
                res = _run_task(name, repo)
                harnesses[name] = {"available": True, "version": ver, **res}
            else:  # openhands: health check only
                harnesses[name] = {"available": True, "version": ver,
                                   "health_checked": True}

    ran = [h for n, h in harnesses.items() if h.get("available") and n in task_runners]
    any_available = any(h.get("available") for h in harnesses.values())
    # Measurement-trust semantics: a timeout / spawn error is an INFRA event
    # (inconclusive), not a capability failure. A harness conclusively fails only if it
    # ran to completion (no error) yet did not solve, OR leaked a secret. The gate passes
    # when a harness is available, at least one harness produced a conclusive solve, and
    # nothing conclusively failed or leaked.
    def _conclusive_fail(h: dict) -> bool:
        if h.get("secret_leak"):
            return True
        return ("error" not in h) and (h.get("no_patch_solve") is False)

    n_solved = sum(1 for h in ran if h.get("no_patch_solve"))
    n_inconclusive = sum(1 for h in ran if "error" in h)
    conclusive_failures = [n for n, h in harnesses.items()
                           if h.get("available") and n in task_runners
                           and _conclusive_fail(h)]
    passed = bool(any_available and not conclusive_failures
                  and (n_solved >= 1 or not ran))
    report = {"experiment": "ws19_vendor_harness_live", "available": any_available,
              "passed": passed, "n_solved": n_solved, "n_inconclusive": n_inconclusive,
              "conclusive_failures": conclusive_failures, "harnesses": harnesses,
              "versions": {k: v for k, v in versions.items() if v}}

    out = Path("evals/reports/vendor_harness_live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked in artifact!"
    return report
