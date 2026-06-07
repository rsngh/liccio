# ruff: noqa: E501
"""Run a vendor-CLI agent harness inside the user-authorized sandbox.

The user authorized spawning the autonomous CLI agents ONLY as the non-root ``claude`` user, inside
throwaway temp dirs, with secrets scrubbed from captured output. This module centralizes that
contract so every CLI policy obeys it. It reuses the argv builders from
:data:`acp.agents.vendor_native.VENDOR_SPECS` but runs the subprocess itself (as ``claude``) so the
shared, tested ``src`` runner is never given root/skip-permission powers.

Env notes pinned during live bring-up:
  * the egress gateway is a TLS-intercepting proxy → the ``claude`` user's Node needs
    ``NODE_EXTRA_CA_CERTS`` or every request dies with SELF_SIGNED_CERT_IN_CHAIN;
  * the Gemini CLI refuses to act in an "untrusted" folder unless ``GEMINI_CLI_TRUST_WORKSPACE`` /
    ``--skip-trust`` is set;
  * the venv must lead ``PATH`` so the agent's ``python -m pytest`` self-check finds pytest.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from acp.agents.vendor_native import VENDOR_SPECS

SANDBOX_USER = "claude"
_CA = "/etc/ssl/certs/ca-certificates.crt"
_VENV_BIN = str(Path(__file__).resolve().parents[2] / ".venv" / "bin")
_BASE_PATH = f"{_VENV_BIN}:/opt/node22/bin:/usr/bin:/bin"


@dataclass
class CliRun:
    ran: bool
    wall_s: float
    timed_out: bool
    error: str | None
    secret_leak: bool
    output_tail: str  # scrubbed, short


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


def grant_access(repo: Path) -> None:
    """Let the non-root agent read/write the throwaway repo AND traverse every ancestor up to /tmp.

    Python's TemporaryDirectory is 700-root, so without opening the ancestor chain the CLI's
    realpath()/lstat() of the workspace dies with EACCES before the agent ever starts.
    """
    subprocess.run(["chmod", "-R", "777", str(repo)], check=False)
    p = repo.parent
    while True:
        try:
            p.chmod(p.stat().st_mode | 0o055)  # +rx for group/other (traverse only)
        except OSError:
            break
        if str(p) in ("/tmp", "/", str(p.parent)):
            break
        p = p.parent


def sandbox_available() -> bool:
    """The claude sandbox user must exist and `sudo -u claude` must work."""
    try:
        import pwd
        pwd.getpwnam(SANDBOX_USER)
    except KeyError:
        return False
    r = subprocess.run(["sudo", "-n", "-u", SANDBOX_USER, "true"], capture_output=True)
    return r.returncode == 0


def run_cli(vendor: str, repo: Path, prompt: str, *, api_env: dict[str, str],
            timeout_s: int = 240) -> CliRun:
    """Run the vendor CLI agent as the sandboxed `claude` user inside `repo`. Never raises."""
    spec = VENDOR_SPECS[vendor]
    if spec.argv_fn is None:
        return CliRun(False, 0.0, False, "not a task runner", False, "")
    # the agent (uid 999) must be able to read+write the repo AND traverse its ancestors
    grant_access(repo)
    env = {
        "HOME": f"/home/{SANDBOX_USER}",
        "PATH": _BASE_PATH,
        "NODE_EXTRA_CA_CERTS": _CA,
        "SSL_CERT_FILE": _CA,
        "GEMINI_CLI_TRUST_WORKSPACE": "true",
        **api_env,
    }
    argv = ["sudo", "-n", "-u", SANDBOX_USER, "env", *[f"{k}={v}" for k, v in env.items()],
            *spec.argv_fn(repo, prompt)]
    t0 = time.monotonic()
    out_text = ""
    timed_out = False
    error: str | None = None
    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout_s)
        out_text = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        timed_out = True
        error = "timeout"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:200]
    wall = round(time.monotonic() - t0, 2)
    leak = _secret_leak(out_text)
    return CliRun(ran=True, wall_s=wall, timed_out=timed_out, error=error,
                  secret_leak=leak, output_tail=_scrub(out_text)[-400:])


def cleanup(repo: Path) -> None:
    shutil.rmtree(repo, ignore_errors=True)
