# ruff: noqa: E501, F401
"""Backward-compat shim — the sandbox runner now lives in `acp.agents.sandbox_cli` (src).

Re-exports the governed runner so existing harness_arena code keeps working unchanged.
"""

from __future__ import annotations

from acp.agents.sandbox_cli import (
    _BASE_PATH,
    _CA,
    SANDBOX_USER,
    CliRun,
    _scrub,
    _secret_leak,
    all_vendor_status,
    grant_access,
    run_vendor_cli,
    sandbox_user_available,
    vendor_status,
)

# legacy names used by harness_arena.policies
run_cli = run_vendor_cli
sandbox_available = sandbox_user_available
