"""Gemini agent adapter — optional, lazy, dependency-free (stdlib HTTP via httpx).

A genuinely *different provider* than Claude, so the metarouter's heterogeneity claim can be tested
across model families (not just Anthropic tiers). Mirrors :class:`ClaudeAgentAdapter`'s single-shot
contract: returns a normalized ``AgentAttemptResult`` with a diff + token counts, or a structured
FAILED result when the key/SDK/network is missing. Reads ``GEMINI_API_KEY`` /
``ACP_GEMINI_API_KEY``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from acp.core.enums import AgentKind, RunStatus
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

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiAgentAdapter:
    kind = AgentKind.GEMINI
    is_harness = False

    def __init__(self, name: str = "gemini", model: str = "gemini-2.5-flash",
                 max_output_tokens: int = 8192, thinking_budget: int | None = None,
                 temperature: float = 0.0) -> None:
        self.name = name
        self.model_name = model
        self.max_output_tokens = max_output_tokens
        # gemini 2.5+ thinking: None = model default, 0 = off, >0 = explicit budget tokens
        self.thinking_budget = thinking_budget
        self.temperature = temperature   # >0 gives sampling diversity for self-ensembles

    def _api_key(self) -> str | None:
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("ACP_GEMINI_API_KEY")

    def _http(self):
        try:
            import httpx
        except ImportError:
            return None
        return httpx

    async def healthcheck(self) -> AgentHealth:
        ok = self._api_key() is not None and self._http() is not None
        return AgentHealth(name=self.name, kind=self.kind, available=ok,
                           detail="ok" if ok else "httpx or GEMINI_API_KEY missing")

    async def plan(self, task: Task, context_pack: ContextPack, workspace: Workspace,
                   budget: Budget) -> AgentPlan:
        return AgentPlan(summary=f"gemini plan for {task.title}")

    async def execute(self, task: Task, context_pack: ContextPack, workspace: Workspace,
                      budget: Budget) -> AgentAttemptResult:
        t0 = time.monotonic()
        httpx = self._http()
        key = self._api_key()
        if httpx is None or key is None:
            return AgentAttemptResult(status=RunStatus.FAILED, error="gemini unavailable",
                                      wall_time_s=time.monotonic() - t0)
        prompt = (
            "You are a senior engineer. Return ONLY JSON "
            '{"files": {"path": "full new content"}} implementing the task minimally. '
            "No prose, no markdown fences.\n\n"
            f"{context_pack.render_markdown()[:12000]}"
        )
        gen_cfg: dict = {"maxOutputTokens": self.max_output_tokens, "temperature": self.temperature}
        if self.thinking_budget is not None:
            # explicit thinking budget (0 disables thinking on 2.5-flash; >0 sets the budget)
            gen_cfg["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }
        try:
            timeout = min(float(getattr(budget, "max_wall_time_s", 60) or 60), 120)
            resp = httpx.post(_ENDPOINT.format(model=self.model_name),
                              params={"key": key}, json=payload, timeout=timeout)
            data = resp.json()
            if "error" in data:
                return AgentAttemptResult(status=RunStatus.FAILED,
                                          error=str(data["error"].get("message", ""))[:200],
                                          wall_time_s=time.monotonic() - t0)
            cand = (data.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            usage = data.get("usageMetadata", {})
            in_tok = usage.get("promptTokenCount", 0)
            # thinking models billed for reasoning ("thought") tokens AS output — count them
            out_tok = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
            if not text:
                # thinking models can exhaust the budget on reasoning with no emitted code
                return AgentAttemptResult(
                    status=RunStatus.FAILED,
                    error=f"empty output (finish={cand.get('finishReason')})",
                    input_token_count=in_tok, output_token_count=out_tok,
                    wall_time_s=time.monotonic() - t0)
            payload_files = json.loads(_extract_json(text)).get("files") or {}
            root = Path(workspace.path)
            for rel, content in payload_files.items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            cap = DiffCapturer(str(root), workspace.spec.base_commit)
            return AgentAttemptResult(
                status=RunStatus.SUCCEEDED,
                diff=DiffBundleRef(unified_diff=cap.get_unified_diff(),
                                   changed_files=cap.get_changed_files()),
                input_token_count=in_tok, output_token_count=out_tok,
                wall_time_s=time.monotonic() - t0)
        except Exception as exc:  # noqa: BLE001 - structured failure (network/json/etc.)
            return AgentAttemptResult(status=RunStatus.FAILED, error=str(exc)[:200],
                                      wall_time_s=time.monotonic() - t0)

    async def review(self, task: Task, diff: DiffBundle, context_pack: ContextPack,
                     budget: Budget) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.2)


def _extract_json(text: str) -> str:
    # tolerate ```json fences and surrounding prose
    if "```" in text:
        chunk = text.split("```", 2)
        text = chunk[1][4:] if len(chunk) > 1 and chunk[1].startswith("json") else (
            chunk[1] if len(chunk) > 1 else text)
    start, end = text.find("{"), text.rfind("}")
    return text[start: end + 1] if start >= 0 and end > start else "{}"
