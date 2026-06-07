# ruff: noqa: E501
"""Governed vendor-CLI harness adapter (Code as Agent Harness, 2605.18747).

Promotes the eval-only sandbox runner into a first-class ``src`` surface so the router can dispatch
the real autonomous agents — Gemini CLI, OpenHands, Codex, Claude Code — under one contract, with
**availability separated from capability**: a vendor that cannot run *here* (binary absent, network
blocked, read-only mount) reports ``available=False`` with a reason and is skipped, never faked.
When the environment allows it, the same lever activates with no code change.

User-authorized sandbox contract: the autonomous agents run only as the non-root ``claude`` user,
inside throwaway temp dirs, with the egress CA cert passed through and secrets scrubbed from output.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from acp.agents.vendor_native import VENDOR_SPECS

SANDBOX_USER = "claude"
_CA = "/etc/ssl/certs/ca-certificates.crt"
_BASE_PATH = f"{sys.prefix}/bin:/opt/node22/bin:/usr/bin:/bin"
_OH_VENV = Path("/tmp/ohvenv/bin/python")

# which backing credential / reachability each vendor needs (for honest availability reporting)
VENDOR_BACKING = {
    "gemini_cli": ("GEMINI_API_KEY", "gemini"),       # Google CLI agent
    "openhands": ("GEMINI_API_KEY", None),            # OpenHands V1 local runtime (litellm backend)
    "codex_cli": ("OPENAI_API_KEY", "codex"),         # OpenAI Codex CLI
    "claude_code": ("ANTHROPIC_API_KEY", "claude"),   # Anthropic Claude Code CLI
}


@dataclass
class CliRun:
    ran: bool
    wall_s: float
    timed_out: bool
    error: str | None
    secret_leak: bool
    output_tail: str


@dataclass
class VendorStatus:
    vendor: str
    available: bool
    reason: str


def _scrub(text: str) -> str:
    for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(key)
        if v:
            text = text.replace(v, "<REDACTED>")
    return re.sub(r"(sk-[A-Za-z0-9_\-]{12,}|AIza[A-Za-z0-9_\-]{20,})", "<REDACTED>", text)


def _secret_leak(text: str) -> bool:
    for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(key)
        if v and v in (text or ""):
            return True
    return bool(re.search(r"sk-[A-Za-z0-9]{20,}", text or ""))


def sandbox_user_available() -> bool:
    try:
        import pwd
        pwd.getpwnam(SANDBOX_USER)
    except KeyError:
        return False
    return subprocess.run(["sudo", "-n", "-u", SANDBOX_USER, "true"], capture_output=True).returncode == 0


def _binary_runnable_by_sandbox(binary: str) -> tuple[bool, str]:
    """A vendor CLI is only usable if the sandbox user can actually execute its binary.

    Catches the Claude Code case: the binary is on PATH but lives behind a read-only 700-root mount,
    so the non-root agent can't reach it (and the CLI refuses --dangerously-skip-permissions as root).
    """
    path = shutil.which(binary)
    if path is None:
        return False, f"{binary} binary not installed"
    r = subprocess.run(["sudo", "-n", "-u", SANDBOX_USER, "env",
                        f"PATH={_BASE_PATH}", binary, "--version"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        why = (r.stderr or r.stdout or "").strip().splitlines()
        return False, f"{binary} not runnable as sandbox user: {(why[-1] if why else 'exec failed')[:80]}"
    return True, "ok"


def vendor_status(vendor: str) -> VendorStatus:
    """Honest, env-aware availability for one vendor (availability != capability)."""
    if vendor not in VENDOR_SPECS:
        return VendorStatus(vendor, False, "unknown vendor")
    key_name, binary = VENDOR_BACKING.get(vendor, (None, None))
    if key_name and not os.environ.get(key_name):
        return VendorStatus(vendor, False, f"{key_name} not set")
    if not sandbox_user_available():
        return VendorStatus(vendor, False, "sandbox user unavailable")
    if vendor == "openhands":
        if not _OH_VENV.exists():
            return VendorStatus(vendor, False, "openhands venv not installed")
        return VendorStatus(vendor, True, "ok (local runtime)")
    if binary:
        ok, reason = _binary_runnable_by_sandbox(binary)
        return VendorStatus(vendor, ok, reason)
    return VendorStatus(vendor, False, "no runner")


def all_vendor_status() -> dict[str, VendorStatus]:
    return {v: vendor_status(v) for v in VENDOR_BACKING}


def grant_access(repo: Path) -> None:
    """Let the non-root agent read/write the repo AND traverse every ancestor up to /tmp."""
    subprocess.run(["chmod", "-R", "777", str(repo)], check=False)
    p = repo.parent
    while True:
        try:
            p.chmod(p.stat().st_mode | 0o055)
        except OSError:
            break
        if str(p) in ("/tmp", "/", str(p.parent)):
            break
        p = p.parent


def run_vendor_cli(vendor: str, repo: Path, prompt: str, *, api_env: dict[str, str],
                   timeout_s: int = 240) -> CliRun:
    """Run the vendor CLI agent as the sandboxed ``claude`` user inside ``repo``. Never raises."""
    spec = VENDOR_SPECS[vendor]
    if spec.argv_fn is None:
        return CliRun(False, 0.0, False, "not a task runner", False, "")
    grant_access(repo)
    env = {"HOME": f"/home/{SANDBOX_USER}", "PATH": _BASE_PATH, "NODE_EXTRA_CA_CERTS": _CA,
           "SSL_CERT_FILE": _CA, "GEMINI_CLI_TRUST_WORKSPACE": "true", **api_env}
    argv = ["sudo", "-n", "-u", SANDBOX_USER, "env", *[f"{k}={v}" for k, v in env.items()],
            *spec.argv_fn(repo, prompt)]
    t0 = time.monotonic()
    out_text, timed_out, error = "", False, None
    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout_s)
        out_text = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        timed_out, error = True, "timeout"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:200]
    return CliRun(ran=True, wall_s=round(time.monotonic() - t0, 2), timed_out=timed_out,
                  error=error, secret_leak=_secret_leak(out_text), output_tail=_scrub(out_text)[-400:])
