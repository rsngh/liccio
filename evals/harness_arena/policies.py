# ruff: noqa: E501
"""Harness-arena policies — route across AGENT HARNESSES on one task + one held-out verifier.

Each policy fixes the same buggy repo and is graded by the SAME hidden test (never shown to the
agent). What differs is the *harness*:

  * ``single_shot``    — one Claude model call, minimal context (the lever-free control).
  * ``inproc_harness`` — ACP's in-process Claude tool-loop harness (read/write/run tools).
  * ``gemini_cli``     — Google's real ``gemini`` CLI agent, autonomous, sandboxed.
  * ``openhands``      — OpenHands V1 local-runtime agent (Gemini backend), autonomous, sandboxed.

The autonomous harnesses can grep/read the whole repo, so on cross-file "ceiling" tasks they may
discover the answer file a single-shot call can never see — the experiment's core question.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from evals.harness_arena import sandbox
from evals.metarouter_arena.policies import build_workspace, verify
from evals.metarouter_arena.schema import AdapterStatus, ArenaAttempt, ArenaTaskSpec

_OH_VENV = Path("/tmp/ohvenv/bin/python")
_PROJECT = str(Path(__file__).resolve().parents[2])


def _prompt(spec: ArenaTaskSpec) -> str:
    return (f"{spec.issue_text}\n\nThe repository has a failing test in test_public.py. Fix the bug "
            f"in {spec.module_path} so that test passes. You may read, grep, or list ANY file in the "
            f"repository to find what you need. Do NOT edit any test file. When the fix is done, stop.")


# --- baselines that reuse the metarouter arena (Claude family) -------------------------------

def policy_single_shot(spec: ArenaTaskSpec, root: Path, *, claude_single=None, **_) -> ArenaAttempt:
    from evals.metarouter_arena.policies import _single_shot
    if claude_single is None:
        return _unavail(spec, "single_shot")
    att = _single_shot(claude_single, spec, root, strategy="minimal", policy_name="single_shot")
    att.policy = "single_shot"
    return att


def policy_inproc_harness(spec: ArenaTaskSpec, root: Path, *, claude_harness=None, **_) -> ArenaAttempt:
    from evals.metarouter_arena.policies import policy_claude_harness
    if claude_harness is None:
        return _unavail(spec, "inproc_harness")
    att = policy_claude_harness(spec, root, claude_harness=claude_harness)
    att.policy = "inproc_harness"
    return att


# --- autonomous vendor harnesses (sandboxed as the claude user) ------------------------------

def _verify_cli_result(spec, ws, call_root, *, policy, ran, t0, cost=0.0, tool_calls=0,
                       extra="") -> ArenaAttempt:
    """Shared tail: grade the agent's in-place edits with the held-out hidden test."""
    if ran.secret_leak:
        return ArenaAttempt(task=spec.name, policy=policy,
                            adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value, solved=False,
                            public_solved=False, conclusive=True, cost_usd=cost,
                            latency_s=round(time.time() - t0, 2), detail="secret_leak->fail")
    if not ran.ran or (ran.error and ran.error != "timeout"):
        return ArenaAttempt(task=spec.name, policy=policy,
                            adapter_status=AdapterStatus.LIVE_INCONCLUSIVE.value, solved=False,
                            public_solved=False, conclusive=False, cost_usd=0.0,
                            latency_s=round(time.time() - t0, 2), detail=f"infra: {ran.error}")
    solved, public = verify(ws, spec, call_root)
    return ArenaAttempt(task=spec.name, policy=policy,
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value, solved=solved,
                        public_solved=public, conclusive=True, cost_usd=round(cost, 6),
                        latency_s=round(time.time() - t0, 2), tool_calls=tool_calls,
                        detail=("timeout; " if ran.timed_out else "") + extra)


def policy_gemini_cli(spec: ArenaTaskSpec, root: Path, *, gemini_key=None, **_) -> ArenaAttempt:
    if gemini_key is None or not sandbox.sandbox_available():
        return _unavail(spec, "gemini_cli")
    call_root = root / "gemini_cli" / f"c{time.time_ns()}"
    ws = build_workspace(spec, call_root)
    t0 = time.time()
    ran = sandbox.run_cli("gemini_cli", ws, _prompt(spec),
                          api_env={"GEMINI_API_KEY": gemini_key}, timeout_s=240)
    return _verify_cli_result(spec, ws, call_root, policy="gemini_cli", ran=ran, t0=t0,
                              extra="gemini-2.5-flash CLI")


def policy_openhands(spec: ArenaTaskSpec, root: Path, *, gemini_key=None, **_) -> ArenaAttempt:
    if gemini_key is None or not sandbox.sandbox_available() or not _OH_VENV.exists():
        return _unavail(spec, "openhands")
    call_root = root / "openhands" / f"c{time.time_ns()}"
    ws = build_workspace(spec, call_root)
    sandbox.grant_access(ws)
    env = {"HOME": "/home/" + sandbox.SANDBOX_USER, "GEMINI_API_KEY": gemini_key,
           "OPENHANDS_SUPPRESS_BANNER": "1", "PYTHONPATH": _PROJECT,
           "SSL_CERT_FILE": sandbox._CA, "REQUESTS_CA_BUNDLE": sandbox._CA,
           "PATH": "/tmp/ohvenv/bin:/usr/bin:/bin"}
    argv = ["sudo", "-n", "-u", sandbox.SANDBOX_USER, "env", *[f"{k}={v}" for k, v in env.items()],
            str(_OH_VENV), "-m", "evals.harness_arena.openhands_driver", str(ws),
            "gemini/gemini-2.5-flash", _prompt(spec)]
    t0 = time.time()
    timed_out = False
    error = None
    out = ""
    try:
        proc = subprocess.run(argv, cwd=ws, capture_output=True, text=True, timeout=300)
        out = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        timed_out = True
        error = "timeout"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:200]
    cost = _parse_oh_cost(out)
    leak = sandbox._secret_leak(out)
    ran = sandbox.CliRun(ran=bool(out) or error is None, wall_s=round(time.time() - t0, 2),
                         timed_out=timed_out, error=error, secret_leak=leak, output_tail="")
    return _verify_cli_result(spec, ws, call_root, policy="openhands", ran=ran, t0=t0,
                              cost=cost, extra="OpenHands local/gemini")


def _parse_oh_cost(out: str) -> float:
    # OpenHands prints a running "$ <amount>" cost line; take the last occurrence
    matches = re.findall(r"\$\s*([0-9]+\.[0-9]+)", out)
    return float(matches[-1]) if matches else 0.0


def _unavail(spec: ArenaTaskSpec, policy: str) -> ArenaAttempt:
    return ArenaAttempt(task=spec.name, policy=policy,
                        adapter_status=AdapterStatus.UNAVAILABLE.value, solved=False,
                        public_solved=False, conclusive=False, cost_usd=0.0, latency_s=0.0,
                        detail="unavailable")


ALL_POLICIES = {
    "single_shot": policy_single_shot,
    "inproc_harness": policy_inproc_harness,
    "gemini_cli": policy_gemini_cli,
    "openhands": policy_openhands,
}
