"""SimpleLLM adapter (charter §12) — optional, OpenAI-backed.

Lazy-imports ``openai`` and requires an API key. Without either, healthcheck
reports unavailable and the adapter is filtered out of routing. Used both as a
lightweight code agent and a reviewer. Live-tested when ACP_OPENAI_API_KEY set.
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


class SimpleLLMReviewAdapter:
    kind = AgentKind.SIMPLE_LLM

    def __init__(self, name: str = "simple_llm", model: str = "gpt-4o-mini") -> None:
        self.name = name
        self.model_name = model

    def _client(self):
        openai = try_import("openai")
        if openai is None:
            return None
        key = get_settings().openai_api_key
        if key is None:
            return None
        return openai.OpenAI(api_key=key.get_secret_value())

    async def healthcheck(self) -> AgentHealth:
        client = self._client()
        return AgentHealth(
            name=self.name,
            kind=self.kind,
            available=client is not None,
            detail="ok" if client is not None else "openai SDK or ACP_OPENAI_API_KEY missing",
        )

    async def plan(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentPlan:
        return AgentPlan(summary=f"LLM plan for {task.title}")

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        client = self._client()
        if client is None:
            return AgentAttemptResult(
                status=RunStatus.FAILED, error="LLM unavailable", wall_time_s=time.monotonic() - t0
            )
        prompt = (
            "You are a coding agent. Given the task and context, return JSON "
            '{"files": {"path": "full new content"}} with the minimal edit.\n\n'
            f"{context_pack.render_markdown()[:12000]}"
        )
        try:
            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            payload = json.loads(resp.choices[0].message.content or "{}")
            usage = getattr(resp, "usage", None)
            root = Path(workspace.path)
            for rel, content in (payload.get("files") or {}).items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            cap = DiffCapturer(str(root), workspace.spec.base_commit)
            return AgentAttemptResult(
                status=RunStatus.SUCCEEDED,
                diff=DiffBundleRef(
                    unified_diff=cap.get_unified_diff(), changed_files=cap.get_changed_files()
                ),
                input_token_count=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_token_count=getattr(usage, "completion_tokens", 0) if usage else 0,
                wall_time_s=time.monotonic() - t0,
            )
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            return AgentAttemptResult(
                status=RunStatus.FAILED, error=str(exc), wall_time_s=time.monotonic() - t0
            )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        client = self._client()
        if client is None:
            return AgentReviewResult(verdict="uncertain", confidence=0.0)
        return AgentReviewResult(verdict="uncertain", confidence=0.2)
