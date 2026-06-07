"""Claude agent adapter (charter §12.4) — optional, lazy.

Wraps the Claude Agent SDK / Anthropic SDK when installed and a key is present.
Without either, healthcheck reports unavailable and project import never fails.
Token/cost captured when the SDK reports it; otherwise estimated.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from acp.core.config import get_settings
from acp.core.enums import AgentKind, RunStatus
from acp.core.optional import try_import
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
    DiffBundleRef,
)
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.workspaces.base import Workspace
from acp.workspaces.diff import DiffCapturer


class ClaudeAgentAdapter:
    kind = AgentKind.CLAUDE
    is_harness = False  # simple model adapter, not a full tool-loop harness

    def __init__(self, name: str = "claude", model: str = "claude-sonnet-4-6",
                 thinking_budget: int = 0) -> None:
        self.name = name
        self.model_name = model
        self.thinking_budget = thinking_budget  # extended-thinking token budget (0 = off)

    def _client(self):
        anthropic = try_import("anthropic")
        if anthropic is None:
            return None
        key = get_settings().anthropic_api_key
        if key is None:
            return None
        return anthropic.Anthropic(api_key=key.get_secret_value())

    async def healthcheck(self) -> AgentHealth:
        client = self._client()
        return AgentHealth(
            name=self.name,
            kind=self.kind,
            available=client is not None,
            detail="ok" if client is not None else "anthropic SDK or ACP_ANTHROPIC_API_KEY missing",
        )

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan:
        return AgentPlan(summary=f"claude plan for {task.title}")

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        client = self._client()
        if client is None:
            return AgentAttemptResult(
                status=RunStatus.FAILED, error="claude unavailable",
                wall_time_s=time.monotonic() - t0,
            )
        prompt = (
            "You are a senior engineer. Return ONLY JSON "
            '{"files": {"path": "full new content"}} implementing the task minimally.\n\n'
            f"{context_pack.render_markdown()[:12000]}"
        )
        try:
            kwargs: dict = {"model": self.model_name,
                            "messages": [{"role": "user", "content": prompt}]}
            if self.thinking_budget > 0:
                # extended thinking: max_tokens must exceed the thinking budget; temperature unset
                kwargs["max_tokens"] = self.thinking_budget + 4096
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
            else:
                kwargs["max_tokens"] = 4096
            msg = client.messages.create(**kwargs)
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            payload = json.loads(_extract_json(text))
            root = Path(workspace.path)
            for rel, content in (payload.get("files") or {}).items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            cap = DiffCapturer(str(root), workspace.spec.base_commit)
            usage = getattr(msg, "usage", None)
            return AgentAttemptResult(
                status=RunStatus.SUCCEEDED,
                diff=DiffBundleRef(
                    unified_diff=cap.get_unified_diff(), changed_files=cap.get_changed_files()
                ),
                input_token_count=getattr(usage, "input_tokens", 0) if usage else 0,
                output_token_count=getattr(usage, "output_tokens", 0) if usage else 0,
                wall_time_s=time.monotonic() - t0,
            )
        except Exception as exc:  # noqa: BLE001 - structured failure
            return AgentAttemptResult(
                status=RunStatus.FAILED, error=str(exc), wall_time_s=time.monotonic() - t0
            )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.2)


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else "{}"
