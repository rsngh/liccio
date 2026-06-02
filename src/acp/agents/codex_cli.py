"""Codex CLI vendor harness shim (alpha-6 WS1).

A thin, capability-gated wrapper around the external ``codex`` command-line
coding agent. It is a *vendor harness*, not an ACP true harness: the CLI runs
the agent as a black box and we normalize the run into the standard
:class:`AgentAttemptResult` surface.

It requires a ``codex`` binary on ``PATH``. Without it (as in this environment)
it degrades cleanly: ``healthcheck`` reports unavailable and ``execute`` returns
a clean unavailable result rather than raising.
"""

from __future__ import annotations

from acp.agents.vendor_base import VendorCapability, VendorHarnessAdapter
from acp.core.enums import AgentKind


class CodexCLIAdapter(VendorHarnessAdapter):
    kind = AgentKind.CODEX
    capability = VendorCapability(kind="cli", requirement="codex")

    def __init__(self, name: str = "codex_cli", model: str = "codex") -> None:
        super().__init__(name=name, model=model)
