"""Persisted shadow/guarded decision (Alpha 27 — production shadow store).

A shadow or guarded-execution decision is durable evidence: what ACP recommended for a real
task, the policy dossier behind it, the guarded execution mode it was capped to, and — when a
human reviews it — their accept/reject verdict and the eventual outcome. Persisting these as
DB entities lets ACP build a shadow-decision inbox, measure acceptance rate over time, and —
critically — turn every human OVERRIDE into a training example (the human's correction is a
label the policy can learn from). The ``autonomous_write`` flag is recorded so an audit can
prove no decision wrote without approval.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class ShadowDecisionRecord(ACPModel):
    id: str = Field(default_factory=lambda: new_id("shadow"))
    task_id: str
    task_type: str = "bugfix"
    risk: str = "low"
    action: str = "answer"                  # answer | abstain | ask_for_spec | ...
    allowed_mode: str = "shadow_only"       # guarded-execution mode it was capped to
    recommended_adapter: str | None = None
    autonomous_write: bool = False          # audit: did this decision write? (must be False)
    evidence_tier: str = "live_api"
    dossier: dict = Field(default_factory=dict)
    human_verdict: str | None = None        # accepted | rejected | overridden | None
    human_choice: str | None = None         # what the human picked (for an override)
    observed_outcome: str | None = None     # solved | failed | None
    created_at: datetime = Field(default_factory=utcnow)

    def model_post_init(self, _ctx: Any) -> None:
        # an override implies the human disagreed with the recommendation
        if self.human_verdict == "overridden" and self.human_choice is None:
            object.__setattr__(self, "human_choice", "unspecified")
