"""Claude Agent SDK vendor harness shim (alpha-6 WS1).

A thin, capability-gated wrapper around Anthropic's external coding agent (the
``claude_agent_sdk`` package, or the ``anthropic`` SDK as a fallback) plus a
configured API key. It is a *vendor harness*, not an ACP true harness: the SDK
runs the agent as a black box and we normalize the run into the standard
:class:`AgentAttemptResult` surface.

In an environment without the SDK or key (as here) it degrades cleanly:
``healthcheck`` reports unavailable and ``execute`` returns a clean unavailable
result rather than raising.
"""

from __future__ import annotations

from acp.agents.vendor_base import VendorCapability, VendorHarnessAdapter
from acp.core.enums import AgentKind


class ClaudeAgentSDKAdapter(VendorHarnessAdapter):
    kind = AgentKind.CLAUDE
    capability = VendorCapability(kind="sdk", requirement="claude_agent_sdk",
                                  requires_key=True)

    def __init__(self, name: str = "claude_agent_sdk",
                 model: str = "claude-haiku-4-5") -> None:
        super().__init__(name=name, model=model)

    def _requirement_present(self) -> bool:
        # Accept either the dedicated agent SDK or the base anthropic SDK.
        from acp.core.optional import try_import

        return (try_import("claude_agent_sdk") is not None
                or try_import("anthropic") is not None)

    def _key_present(self) -> bool:
        from acp.core.config import get_settings

        return get_settings().anthropic_api_key is not None
