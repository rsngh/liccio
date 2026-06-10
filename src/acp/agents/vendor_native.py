"""Vendor-native coding harnesses as first-class ACP harnesses (Alpha 22 WS5-9).

Wraps the installed vendor CLIs — Codex, Claude Code, OpenHands — so ACP can drive them
through the same contract as its in-process harnesses: detect availability/version, run a
no-patch fix-the-failing-test task, and capture version/command/cwd/timeout/diff/pytest
result/secret-scan/AgentTrace-like metadata, classified into an AttemptOutcome. OpenHands
is reported by capability LEVEL (health -> launch -> trace -> solve) without overclaiming.
Unavailable harnesses are skipped, not failed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VendorSpec:
    name: str
    binary: str
    version_args: list[str]
    # builds the headless argv to fix the bug in `repo`; None == not a task runner
    argv_fn: Callable[[Path, str], list[str]] | None = None
    needs_cwd: bool = False  # run with cwd=repo (claude) vs --cd flag (codex)


def _codex_argv(repo: Path, prompt: str) -> list[str]:
    return ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check",
            "--cd", str(repo), prompt]


def _claude_argv(repo: Path, prompt: str) -> list[str]:
    # acceptEdits auto-applies file edits non-interactively WITHOUT the unsafe
    # --dangerously-skip-permissions autonomous mode (read/edit tools only; no blanket bash).
    # Claude Code solves these well at low effort, so default to low (fast + quota-light);
    # override with ACP_CLAUDE_EFFORT=medium|high if a hard bundle needs more.
    effort = os.environ.get("ACP_CLAUDE_EFFORT", "low")
    return ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--effort", effort,
            "--allowedTools", "Edit", "Write", "Read", "Grep", "Glob"]


def _gemini_argv(repo: Path, prompt: str) -> list[str]:
    # headless, auto-approve all tools; --skip-trust so a fresh workspace runs unattended
    return ["gemini", "-m", "gemini-2.5-flash", "--skip-trust", "--yolo", "-p", prompt]


VENDOR_SPECS: dict[str, VendorSpec] = {
    "codex_cli": VendorSpec("codex_cli", "codex", ["--version"], _codex_argv),
    "claude_code": VendorSpec("claude_code", "claude", ["--version"], _claude_argv,
                              needs_cwd=True),
    "gemini_cli": VendorSpec("gemini_cli", "gemini", ["--version"], _gemini_argv,
                             needs_cwd=True),
    "openhands": VendorSpec("openhands", "openhands", ["--version"], None),
}

_HOST_CA = "/etc/ssl/certs/ca-certificates.crt"


def vendor_env(name: str) -> dict[str, str]:
    """Subprocess env for a vendor CLI run.

    * Every node-based CLI gets ``NODE_EXTRA_CA_CERTS`` so it trusts the host/proxy CA bundle.
    * ``claude_code`` runs on the **Claude subscription (OAuth)**, so ``ANTHROPIC_API_KEY`` /
      ``ACP_ANTHROPIC_API_KEY`` are STRIPPED — when that env var is present Claude Code silently
      switches to API-key billing instead of the logged-in subscription.
    * ``gemini_cli`` gets ``GEMINI_CLI_TRUST_WORKSPACE`` so a fresh workspace runs headless.
    """
    env = dict(os.environ)
    if os.path.exists(_HOST_CA):
        env.setdefault("NODE_EXTRA_CA_CERTS", _HOST_CA)
    if name == "claude_code":
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ACP_ANTHROPIC_API_KEY", None)
    if name == "gemini_cli":
        env.setdefault("GEMINI_CLI_TRUST_WORKSPACE", "true")
    return env


def detect_vendor_health() -> dict:
    """WS5: per-harness {available, version}. Unavailable -> available False (skip)."""
    out: dict = {}
    for name, spec in VENDOR_SPECS.items():
        if shutil.which(spec.binary) is None:
            out[name] = {"available": False}
            continue
        try:
            r = subprocess.run([spec.binary, *spec.version_args], capture_output=True,
                               text=True, timeout=30)
            line = (r.stdout or r.stderr or "").strip().splitlines()
            out[name] = {"available": True,
                         "version": line[0].strip() if line else "unknown"}
        except Exception:  # noqa: BLE001
            out[name] = {"available": False}
    return out


# WS6: the no-patch smoke fixture — a real failing-test repo the harness must fix.
_CALC = ("def add(a, b):\n    return a + b\n\n\n"
         "def divide(a, b):\n    return a + b  # BUG: should be a / b\n")
_TEST = ("import pytest\n\nfrom calculator import add, divide\n\n\n"
         "def test_add():\n    assert add(2, 3) == 5\n\n\n"
         "def test_divide():\n    assert divide(6, 2) == 3\n    assert divide(9, 3) == 3\n")
_PROMPT = ("Fix the bug in calculator.py so the failing test in tests/test_calculator.py "
           "passes: divide(a, b) must divide, not add. Then run `python -m pytest -q` to "
           "confirm all tests pass before finishing.")


def build_smoke_fixture(root: Path) -> Path:
    """Create the no-patch smoke repo (calculator + a failing divide test)."""
    repo = root / "calc_repo"
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "calculator.py").write_text(_CALC)
    (repo / "tests" / "test_calculator.py").write_text(_TEST)
    (repo / "tests" / "__init__.py").write_text("")
    # this env enforces signed commits via a signing server; disable so the fixture commit works
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"],
                 ["git", "config", "commit.gpgsign", "false"],
                 ["git", "config", "tag.gpgsign", "false"], ["git", "add", "-A"],
                 ["git", "-c", "commit.gpgsign=false", "commit", "--no-gpg-sign", "-qm", "init"]):
        subprocess.run(argv, cwd=repo, check=False)
    return repo


def _secret_leak(text: str) -> bool:
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret and secret in (text or ""):
            return True
    return bool(re.search(r"sk-[A-Za-z0-9]{20,}", text or ""))


@dataclass
class VendorRunResult:
    harness: str
    version: str
    command: list[str] = field(default_factory=list)
    cwd: str = ""
    timeout_s: int = 0
    wall_time_s: float = 0.0
    no_patch_solve: bool = False
    diff_captured: bool = False
    trace_captured: bool = False
    pytest_passed: bool = False
    secret_leak: bool = False
    timed_out: bool = False
    error: str | None = None
    outcome: str = "inconclusive"
    skill_injected: bool = False
    skill_used_observed: str = "unknown"  # "true" | "false" | "unknown"
    task_type: str = "bugfix"
    task_name: str = "smoke"

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    def to_cell(self) -> dict:
        """A measurement-trust attempt cell for classification / matrix eligibility (WS11)."""
        return {
            "adapter": self.harness, "task_type": self.task_type, "is_harness": True,
            "success": self.no_patch_solve,
            "status": "timed_out" if self.timed_out else (
                "succeeded" if self.no_patch_solve else "failed"),
            "timed_out": self.timed_out, "error": self.error,
            "tool_calls": 1 if (self.diff_captured or self.no_patch_solve) else 0,
            "commands": 1 if self.pytest_passed else 0,
            "file_reads": 1 if self.diff_captured else 0,
            "cost_usd": 0.0,
        }


class VendorNativeHarness:
    """A native ACP harness over a vendor CLI (WS7/8)."""

    def __init__(self, name: str) -> None:
        if name not in VENDOR_SPECS:
            raise ValueError(f"unknown vendor harness {name}")
        self.spec = VENDOR_SPECS[name]

    def available(self) -> bool:
        return shutil.which(self.spec.binary) is not None

    def version(self) -> str | None:
        return detect_vendor_health().get(self.spec.name, {}).get("version")

    def run_smoke(self, repo: Path, *, timeout_s: int = 240,
                  skill_content: str | None = None) -> VendorRunResult:
        """Run the no-patch fix on ``repo`` and capture the full contract.

        If ``skill_content`` is given it is written as SKILL.md into the repo and the
        prompt is prefixed with it (WS10 skill injection), so the vendor harness can read
        and follow it; ``skill_used_observed`` records whether use was observed.
        """
        return self.run_task(repo, _PROMPT, timeout_s=timeout_s,
                             skill_content=skill_content)

    def run_task(self, repo: Path, prompt: str, *, task_type: str = "bugfix",
                 task_name: str = "smoke", timeout_s: int = 240,
                 skill_content: str | None = None) -> VendorRunResult:
        """Drive the harness on an arbitrary bugfix ``prompt`` in ``repo`` (Alpha 23 WS3).

        Generalizes :meth:`run_smoke` to any task (e.g. the graded benchmark suite):
        captures the same full contract — version/command/cwd/timeout/diff/pytest/secret-
        scan — and classifies into an AttemptOutcome. ``skill_content`` injects SKILL.md
        and prefixes the prompt exactly as the smoke path does.
        """
        ver = self.version() or "unknown"
        res = VendorRunResult(harness=self.spec.name, version=ver, cwd=str(repo),
                              timeout_s=timeout_s, task_type=task_type,
                              task_name=task_name)
        if self.spec.argv_fn is None:
            res.error = "not a task runner (health-check only)"
            return res
        if skill_content and skill_content.strip():
            (repo / "SKILL.md").write_text(skill_content)
            prompt = (f"Follow this skill:\n{skill_content}\n\n{prompt}")
            res.skill_injected = True
        argv = self.spec.argv_fn(repo, prompt)
        res.command = argv
        out_text = ""
        t0 = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True,
                                  timeout=timeout_s, env=vendor_env(self.spec.name))
            out_text = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            res.timed_out = True
            res.error = "timeout"
        except Exception as exc:  # noqa: BLE001
            res.error = str(exc)[:200]
        res.wall_time_s = round(time.monotonic() - t0, 2)
        res.trace_captured = bool(out_text) or res.error is None
        diff = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True,
                              check=False).stdout
        res.diff_captured = bool(diff.strip())
        pt = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo,
                            capture_output=True, text=True, check=False)
        res.pytest_passed = pt.returncode == 0
        res.no_patch_solve = res.pytest_passed
        res.secret_leak = _secret_leak(out_text + diff + pt.stdout)
        res.outcome = _classify_vendor(res)
        # WS10: did the harness appear to USE the injected skill? Heuristic — it
        # referenced SKILL.md in its output, or it ran the tests (the skill's directive).
        if res.skill_injected:
            referenced = "SKILL.md" in out_text or "skill" in out_text.lower()
            res.skill_used_observed = "true" if (referenced or res.pytest_passed) \
                else "unknown"
        return res


def _classify_vendor(res: VendorRunResult) -> str:
    """Map a vendor run to an AttemptOutcome value (WS11 measurement-trust)."""
    if res.secret_leak:
        return "task_failure"
    if res.no_patch_solve:
        return "task_success"
    if res.timed_out or res.error:
        return "infra_timeout_before_action"  # infra/budget, inconclusive
    return "task_failure"


# WS9: OpenHands capability level (do not overclaim).
def openhands_capability_level() -> dict:
    """Report the ACTUAL OpenHands capability level reached (1 health .. 4 solve)."""
    if shutil.which("openhands") is None:
        return {"available": False, "level": 0, "label": "not installed"}
    health = detect_vendor_health().get("openhands", {})
    if not health.get("available"):
        return {"available": False, "level": 0, "label": "version probe failed"}
    return {"available": True, "level": 1, "label": "version/health available",
            "version": health.get("version")}
