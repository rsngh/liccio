"""Harness activation / adherence metrics (alpha 11/12 WS6).

Derives, from normalized :class:`~acp.schemas.trace.AgentTrace` signals, whether
a true tool-loop harness actually *engaged* its loop (activation) and *followed*
the read/edit/verify protocol (adherence) — both orthogonal to whether the task
was solved. The roll-up :func:`harness_benefit_metrics` reports HAR / HFR / PWL
overall and sliced by task_type and model so a harness's marginal benefit is
visible per cell.

Pure-python and deterministic: no DB, no network. The synthetic dataset from
:func:`default_harness_metrics_dataset` exercises the activated/solved,
activated/unsolved and not-activated cases used by the tests.
"""

from __future__ import annotations

from acp.schemas.harness_metrics import (
    HarnessActivationReport,
    HarnessAdherenceReport,
    HarnessBenefitMetrics,
)
from acp.schemas.trace import AgentTrace


def _task_type(trace: AgentTrace) -> str:
    """Best-effort task_type from trace metadata (traces don't carry it natively)."""
    tt = trace.metadata.get("task_type")
    return str(tt) if tt else "unknown"


def activation_report(trace: AgentTrace) -> HarnessActivationReport:
    """Did this harness engage its tool loop?

    A harness ACTIVATED when it is flagged ``is_harness`` *and* emitted at least
    one tool call. A simple adapter can never activate (``not_a_harness``); a
    harness with zero tool calls failed to loop (``no_tool_calls``).
    """
    activated = trace.is_harness and trace.tool_calls > 0
    reason: str | None = None
    if not trace.is_harness:
        reason = "not_a_harness"
    elif trace.tool_calls <= 0:
        reason = "no_tool_calls"
    return HarnessActivationReport(
        adapter_name=trace.adapter_name,
        model_name=trace.model_name,
        task_type=_task_type(trace),
        activated=activated,
        activation_failure_reason=reason,
        n_tool_calls=trace.tool_calls,
    )


def adherence_report(trace: AgentTrace) -> HarnessAdherenceReport:
    """Did the harness follow the read/edit/verify protocol?

    FOLLOWED requires that the attempt produced changes (``file_writes`` or
    ``changed_files``) and either ran a command or finished without error.

    ``phase_adherence`` is the mean over three protocol phases that were
    exercised: read (``file_reads`` > 0), write (changes present), and
    run/verify (``commands`` > 0 or no error) — i.e. it rewards a harness that
    looked before it leapt and verified after.

    ``adherence_decay`` is a crude later-phase dropoff proxy: the protocol runs
    read → write → run, so we penalize attempts that completed earlier phases but
    not the final run/verify phase. It is 1.0 when an attempt did the early work
    (read or write) yet skipped run/verify entirely, scaled by how much early
    work it did; 0.0 when it reached the run/verify phase. This flags harnesses
    whose loop "ran out of steam" before verification.
    """
    changed = bool(trace.file_writes) or bool(trace.changed_files)
    ran = trace.commands > 0
    verified = ran or trace.error is None
    followed = changed and verified

    read_phase = trace.file_reads > 0
    write_phase = changed
    run_phase = ran or trace.error is None
    phases = [read_phase, write_phase, run_phase]
    phase_adherence = sum(1 for p in phases if p) / len(phases)

    # later-phase dropoff: early phases done but final run/verify phase skipped.
    early_done = sum(1 for p in (read_phase, write_phase) if p) / 2.0
    reached_run = ran or trace.commands > 0
    adherence_decay = early_done if (early_done > 0.0 and not reached_run) else 0.0

    reason: str | None = None
    if not changed:
        reason = "no_changes"
    elif not verified:
        reason = "no_verification"

    return HarnessAdherenceReport(
        adapter_name=trace.adapter_name,
        model_name=trace.model_name,
        task_type=_task_type(trace),
        followed=followed,
        phase_adherence=round(phase_adherence, 4),
        adherence_decay=round(adherence_decay, 4),
        adherence_failure_reason=reason,
    )


def _rates(
    activated: int, followed: int, solved_when_activated: int, total: int
) -> dict[str, float]:
    """HAR / HFR / PWL for one slice (PWL denominator is activated attempts)."""
    return {
        "har": round(activated / total, 4) if total else 0.0,
        "hfr": round(followed / total, 4) if total else 0.0,
        "pwl": round(solved_when_activated / activated, 4) if activated else 0.0,
    }


def harness_benefit_metrics(
    traces: list[AgentTrace],
    solved_by_attempt: dict[str, bool],
) -> HarnessBenefitMetrics:
    """Roll up HAR / HFR / PWL over the harness attempts in ``traces``.

    Only harness traces (``is_harness``) are counted — benefit metrics are
    undefined for simple adapters. ``solved_by_attempt`` is keyed by
    ``trace.attempt_id``. PWL (pass-when-loaded) is computed only over *activated*
    attempts, so an activated-but-unsolved attempt lowers PWL without affecting
    HAR.
    """
    harness_traces = [t for t in traces if t.is_harness]
    total = len(harness_traces)

    activated = followed = solved_when_activated = 0
    by_tt: dict[str, list[int]] = {}
    by_model: dict[str, list[int]] = {}

    for t in harness_traces:
        act = activation_report(t)
        adh = adherence_report(t)
        is_act = act.activated
        is_fol = adh.followed
        solved = bool(solved_by_attempt.get(t.attempt_id, False))
        act_solved = 1 if (is_act and solved) else 0

        activated += 1 if is_act else 0
        followed += 1 if is_fol else 0
        solved_when_activated += act_solved

        for bucket, key in ((by_tt, act.task_type), (by_model, t.model_name or "unknown")):
            row = bucket.setdefault(key, [0, 0, 0, 0])  # [activated, followed, act_solved, total]
            row[0] += 1 if is_act else 0
            row[1] += 1 if is_fol else 0
            row[2] += act_solved
            row[3] += 1

    by_task_type = {k: _rates(v[0], v[1], v[2], v[3]) for k, v in by_tt.items()}
    by_model_out = {k: _rates(v[0], v[1], v[2], v[3]) for k, v in by_model.items()}
    overall = _rates(activated, followed, solved_when_activated, total)

    return HarnessBenefitMetrics(
        har=overall["har"],
        hfr=overall["hfr"],
        pwl=overall["pwl"],
        by_task_type=by_task_type,
        by_model=by_model_out,
        sample_size=total,
    )


def default_harness_metrics_dataset() -> list[tuple[AgentTrace, bool]]:
    """Synthetic ``(trace, solved)`` pairs covering the WS6 cases (no DB).

    Spans: activated+solved, activated+unsolved, harness-that-never-looped, and a
    simple (non-harness) adapter — across two models and two task types.
    """
    return [
        # activated + solved + adhered (read, write, run)
        (
            AgentTrace(
                attempt_id="a1", adapter_name="claude_harness", is_harness=True,
                model_name="claude-sonnet", status="success", tool_calls=6,
                file_reads=3, file_writes=["src/x.py"], commands=2,
                changed_files=["src/x.py"], diff_lines=20, error=None,
                metadata={"task_type": "bugfix"},
            ),
            True,
        ),
        # activated but unsolved (loop ran, did not solve) -> lowers PWL, not HAR
        (
            AgentTrace(
                attempt_id="a2", adapter_name="claude_harness", is_harness=True,
                model_name="claude-sonnet", status="failed", tool_calls=4,
                file_reads=2, file_writes=["src/y.py"], commands=1,
                changed_files=["src/y.py"], diff_lines=8, error="tests_failed",
                metadata={"task_type": "bugfix"},
            ),
            False,
        ),
        # harness that never engaged its loop (no tool calls) -> not activated
        (
            AgentTrace(
                attempt_id="a3", adapter_name="codex_harness", is_harness=True,
                model_name="gpt-x", status="failed", tool_calls=0,
                file_reads=0, file_writes=[], commands=0, changed_files=[],
                error="loop_init_failed", metadata={"task_type": "feature"},
            ),
            False,
        ),
        # activated + solved on the second model / task type
        (
            AgentTrace(
                attempt_id="a4", adapter_name="codex_harness", is_harness=True,
                model_name="gpt-x", status="success", tool_calls=5,
                file_reads=4, file_writes=["src/z.py"], commands=3,
                changed_files=["src/z.py"], diff_lines=30, error=None,
                metadata={"task_type": "feature"},
            ),
            True,
        ),
        # simple adapter (not a harness) -> excluded from benefit metrics
        (
            AgentTrace(
                attempt_id="a5", adapter_name="simple_llm", is_harness=False,
                model_name="claude-sonnet", status="success", tool_calls=0,
                file_reads=0, file_writes=["src/w.py"], commands=0,
                changed_files=["src/w.py"], diff_lines=12, error=None,
                metadata={"task_type": "bugfix"},
            ),
            True,
        ),
    ]
