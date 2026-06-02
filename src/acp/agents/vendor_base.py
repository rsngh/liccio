"""Base for *vendor* coding-agent harnesses (alpha-6 WS1).

A vendor harness is distinct from an ACP *true* harness (``openai_harness`` /
``claude_harness``, which drive the read/write/run tool loop in-process). A
vendor harness wraps an external coding agent — an SDK or CLI such as the Claude
Agent SDK or the Codex CLI — and runs it as a black box, then *normalizes* its
run into the same :class:`AgentAttemptResult` + trace surface the in-process
harnesses produce. That way a vendor agent shows up in a bakeoff with the same
diff / tool-call / cost / wall-time shape as everything else.

The category vocabulary matches ``docs/status_schema.md``: these adapters are
``vendor harness`` (``category = "vendor"``), ``is_harness=True``.

Every vendor shim declares a :class:`VendorCapability` (what it needs — an SDK
module, a CLI binary, or an API key) and degrades *gracefully*: when the
requirement is absent the adapter reports ``available=False`` and ``execute``
returns a clean unavailable result. It must never raise on import or when its
dependency is missing.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass

from acp.agents.harness_base import finalize_result, make_tools
from acp.core.enums import AgentKind, RunStatus
from acp.core.optional import try_import
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
)
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.workspaces.base import Workspace


@dataclass(frozen=True)
class VendorCapability:
    """What a vendor harness requires to be live.

    ``kind`` is one of ``"sdk"``, ``"cli"`` or ``"api"``; ``requirement`` is the
    importable module name (``sdk``/``api``) or the binary name on ``PATH``
    (``cli``). ``requires_key`` flags adapters that also need a configured API
    key beyond the module/binary being present.
    """

    kind: str
    requirement: str
    requires_key: bool = False


class VendorHarnessAdapter:
    """Base class for vendor coding-agent shims.

    Subclasses set :attr:`kind`, :attr:`capability` and (usually) override
    :meth:`_run_vendor` to drive the external agent. The base handles capability
    detection, graceful unavailability and trace normalization.
    """

    kind: AgentKind
    is_harness = True  # normalized into the same AgentTrace surface as ACP harnesses
    category = "vendor"
    capability: VendorCapability

    def __init__(self, name: str, model: str = "") -> None:
        self.name = name
        self.model_name = model

    # --- capability detection -------------------------------------------------
    def _key_present(self) -> bool:
        """Override in subclasses that need a configured API key."""
        return True

    def _requirement_present(self) -> bool:
        cap = self.capability
        if cap.kind == "cli":
            return shutil.which(cap.requirement) is not None
        # sdk / api: the requirement is an importable module
        return try_import(cap.requirement) is not None

    def available(self) -> bool:
        """True only when the requirement (and key, if needed) are present."""
        if not self._requirement_present():
            return False
        return not (self.capability.requires_key and not self._key_present())

    def _unavailable_detail(self) -> str:
        cap = self.capability
        if not self._requirement_present():
            noun = "binary" if cap.kind == "cli" else "SDK"
            return f"{cap.requirement} {noun} missing"
        return f"{self.name} API key missing"

    async def healthcheck(self) -> AgentHealth:
        ok = self.available()
        return AgentHealth(
            name=self.name, kind=self.kind, available=ok,
            detail="ok" if ok else self._unavailable_detail(),
        )

    async def plan(self, task, context_pack, workspace, budget) -> AgentPlan:
        return AgentPlan(summary=f"vendor harness plan for {task.title}")

    # --- execution ------------------------------------------------------------
    def _run_vendor(
        self, task: Task, context_pack: ContextPack, workspace: Workspace,
        budget: Budget,
    ) -> tuple[int, int, str | None]:
        """Drive the external agent against ``workspace``.

        Returns ``(input_tokens, output_tokens, error)``. The base raises so a
        subclass that reports ``available()`` must implement it; if it cannot,
        it should report unavailable instead.
        """
        raise NotImplementedError

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        if not self.available():
            return AgentAttemptResult(
                status=RunStatus.FAILED,
                error=f"vendor harness unavailable: {self._unavailable_detail()}",
                wall_time_s=time.monotonic() - t0,
                metadata={"category": self.category, "available": False},
            )
        tools = make_tools(workspace)
        session_id = f"sess_{int(t0 * 1000)}"
        in_tok = out_tok = 0
        error: str | None = None
        try:
            in_tok, out_tok, error = self._run_vendor(task, context_pack, workspace, budget)
        except Exception as exc:  # noqa: BLE001 - structured failure, never raise out
            error = str(exc)
        result = finalize_result(
            tools=tools, workspace=workspace, t0=t0, model=self.model_name,
            in_tok=in_tok, out_tok=out_tok, error=error, session_id=session_id,
        )
        result.metadata["category"] = self.category
        return result

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.2)
