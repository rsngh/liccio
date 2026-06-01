"""Agent adapter layer — all adapters behind one protocol."""

from acp.agents.base import AgentAdapter
from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.agents.codex_agent import CodexAgentAdapter
from acp.agents.fake import FakeAgentAdapter
from acp.agents.openai_harness import OpenAIHarnessAdapter
from acp.agents.openhands_agent import OpenHandsAgentAdapter
from acp.agents.patch_agent import PatchAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.agents.simple_llm import SimpleLLMReviewAdapter

__all__ = [
    "AgentAdapter",
    "AgentRegistry",
    "ClaudeAgentAdapter",
    "CodexAgentAdapter",
    "FakeAgentAdapter",
    "OpenAIHarnessAdapter",
    "OpenHandsAgentAdapter",
    "PatchAgentAdapter",
    "SimpleLLMReviewAdapter",
    "build_default_registry",
]


def build_default_registry(include_external: bool = True) -> AgentRegistry:
    """Registry with fake + patch always; external adapters registered but they
    self-report unavailable when their SDK/keys/binaries are missing."""
    reg = AgentRegistry()
    reg.register(FakeAgentAdapter())
    reg.register(PatchAgentAdapter())
    if include_external:
        reg.register(ClaudeAgentAdapter())
        reg.register(CodexAgentAdapter())
        reg.register(OpenHandsAgentAdapter())
        reg.register(SimpleLLMReviewAdapter())
        reg.register(OpenAIHarnessAdapter())
    return reg
