"""Harness activation / adherence metric schemas (alpha 11/12 WS6).

A *true harness* runs a tool loop (read → edit → run → repeat); a *simple
adapter* emits a single JSON edit. Whether the task was solved is one question;
whether the harness actually *engaged its loop* and *followed the protocol* is a
distinct one. These schemas carry those two orthogonal signals plus the rolled-up
harness-benefit metrics (HAR / HFR / PWL) sliced by model / harness / task_type.
"""

from __future__ import annotations

from pydantic import Field

from acp.schemas.base import ACPModel


class HarnessActivationReport(ACPModel):
    """Did a harness *engage* its tool loop on this attempt?

    ``activated`` is true only for a real harness that emitted at least one tool
    call; ``activation_failure_reason`` explains a false (``not_a_harness`` for a
    simple adapter, ``no_tool_calls`` for a harness that never looped).
    """

    adapter_name: str
    model_name: str | None = None
    task_type: str = "unknown"
    activated: bool = False
    activation_failure_reason: str | None = None
    n_tool_calls: int = 0


class HarnessAdherenceReport(ACPModel):
    """Did the harness *follow* the read/edit/verify protocol?

    ``followed`` requires that it both produced changes and either ran a command
    or finished without error. ``phase_adherence`` is a 0..1 score over the
    read/write/run phases; ``adherence_decay`` is a crude later-phase dropoff
    proxy (see :func:`acp.evaluation.harness_metrics.adherence_report`).
    """

    adapter_name: str
    model_name: str | None = None
    task_type: str = "unknown"
    followed: bool = False
    phase_adherence: float = Field(default=0.0, ge=0.0, le=1.0)
    adherence_decay: float = Field(default=0.0, ge=0.0, le=1.0)
    adherence_failure_reason: str | None = None


class HarnessBenefitMetrics(ACPModel):
    """Rolled-up harness benefit over a set of harness attempts.

    - ``har`` (harness activation rate): fraction of harness attempts that
      activated their loop.
    - ``hfr`` (harness following rate): fraction that adhered to the protocol.
    - ``pwl`` (pass-when-loaded rate): fraction of *activated* attempts that
      solved the task — isolating loop benefit from activation failures.

    ``by_task_type`` / ``by_model`` carry the same three rates per slice.
    """

    har: float = Field(default=0.0, ge=0.0, le=1.0)
    hfr: float = Field(default=0.0, ge=0.0, le=1.0)
    pwl: float = Field(default=0.0, ge=0.0, le=1.0)
    by_task_type: dict[str, dict[str, float]] = Field(default_factory=dict)
    by_model: dict[str, dict[str, float]] = Field(default_factory=dict)
    sample_size: int = 0
