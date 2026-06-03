"""Relative trajectory judge (Alpha 11/12 §WS9).

Compares two agent trajectories (:class:`acp.schemas.trace.AgentTrace`) on
multiple independent axes and produces a *relative* preference together with
per-axis rewards. Unlike :mod:`acp.learning.preference`, which fits a model on
absolute per-attempt labels, this judge emits a head-to-head comparison that
preference learning can consume directly as a winner/loser feature pair.

Each axis is an independent judge that scores both trajectories (higher == more
preferred) and declares an axis winner. The overall winner is a configurable
weighted aggregate of the axis verdicts. Two diagnostics build on the result:

* :func:`RelativeTrajectoryJudge.cross_judge_audit` measures how many axes agree
  with the overall winner (judge consensus).
* :func:`RelativeTrajectoryJudge.reward_sensitivity` is a leave-one-axis-out
  study: how often dropping an axis flips the overall winner (its influence).

The security axis reuses the real adversarial detector
(:func:`acp.verification.adversarial.scan_diff`): a trajectory that deletes a
test or tampers with security-sensitive files scores worse. Everything here is
pure-python, deterministic and offline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from acp.learning.preference import Preference
from acp.schemas.trace import AgentTrace
from acp.schemas.trajectory_judge import (
    CrossJudgeAudit,
    PerAxisReward,
    RewardSensitivityReport,
    TrajectoryComparison,
    Winner,
)
from acp.schemas.workspace import DiffBundle
from acp.verification.adversarial import scan_diff, severity_score


@dataclass(frozen=True)
class AxisContext:
    """Per-trajectory inputs that are not carried on the trace itself."""

    solved: bool = False
    diff: DiffBundle | None = None


# An axis judge maps a trace + its context to a score (higher == better).
AxisFn = Callable[[AgentTrace, AxisContext], float]


def _is_test_path(path: str) -> bool:
    low = path.lower()
    return "test" in low and (low.endswith(".py") or ".test." in low or ".spec." in low)


def _axis_goal_achievement(trace: AgentTrace, ctx: AxisContext) -> float:
    """Did the trajectory solve the task?"""
    return 1.0 if ctx.solved else 0.0


def _axis_test_adequacy(trace: AgentTrace, ctx: AxisContext) -> float:
    """Did the trajectory touch / add tests (without removing them)?"""
    touched = sum(1 for p in trace.file_writes if _is_test_path(p))
    deleted = 0
    if ctx.diff is not None:
        deleted = sum(1 for p in ctx.diff.deleted_files if _is_test_path(p))
    return float(touched - deleted)


def _axis_minimality(trace: AgentTrace, ctx: AxisContext) -> float:
    """Smaller diffs are preferred (negated so higher == better)."""
    return -float(trace.diff_lines)


def _axis_security(trace: AgentTrace, ctx: AxisContext) -> float:
    """No test deletion / no security-file tamper (negated severity)."""
    return -severity_score(scan_diff(ctx.diff))


def _axis_harness_activation(trace: AgentTrace, ctx: AxisContext) -> float:
    """Did the harness actually take any tool actions?"""
    return 1.0 if trace.tool_calls > 0 else 0.0


def _axis_harness_adherence(trace: AgentTrace, ctx: AxisContext) -> float:
    """Read + write + run loop exercised (full tool-use repertoire)."""
    return float(
        (1 if trace.file_reads > 0 else 0)
        + (1 if trace.file_writes else 0)
        + (1 if trace.commands > 0 else 0)
    )


def _axis_recovery_behavior(trace: AgentTrace, ctx: AxisContext) -> float:
    """Recovered from an error: hit an error yet still solved the task."""
    return 1.0 if (trace.error and ctx.solved) else 0.0


def _axis_cost(trace: AgentTrace, ctx: AxisContext) -> float:
    """Lower estimated cost is preferred (negated so higher == better)."""
    return -float(trace.estimated_cost_usd)


# Ordered axis registry: name -> judge. Order is stable for determinism.
_AXES: dict[str, AxisFn] = {
    "goal_achievement": _axis_goal_achievement,
    "test_adequacy": _axis_test_adequacy,
    "minimality": _axis_minimality,
    "security": _axis_security,
    "harness_activation": _axis_harness_activation,
    "harness_adherence": _axis_harness_adherence,
    "recovery_behavior": _axis_recovery_behavior,
    "cost": _axis_cost,
}


def _winner_of(score_a: float, score_b: float, *, eps: float = 1e-9) -> Winner:
    if score_a > score_b + eps:
        return "a"
    if score_b > score_a + eps:
        return "b"
    return "tie"


@dataclass
class RelativeTrajectoryJudge:
    """Compares two trajectories on several axes and aggregates a preference.

    ``weights`` maps an axis name to its relative weight in the overall verdict;
    unspecified axes default to ``1.0``. The overall winner is the side with the
    larger weighted axis-vote sum (each axis contributes ``+w`` to its winner,
    ties contribute nothing); ``margin`` is the absolute weighted vote gap.
    """

    weights: dict[str, float] = field(default_factory=dict)
    axes: dict[str, AxisFn] = field(default_factory=lambda: dict(_AXES))

    def _weight(self, axis: str) -> float:
        return float(self.weights.get(axis, 1.0))

    def score_axes(
        self, a: AgentTrace, b: AgentTrace, ctx_a: AxisContext, ctx_b: AxisContext
    ) -> list[PerAxisReward]:
        """Score every axis for both trajectories."""
        rewards: list[PerAxisReward] = []
        for name, fn in self.axes.items():
            sa = fn(a, ctx_a)
            sb = fn(b, ctx_b)
            rewards.append(
                PerAxisReward(
                    axis=name,
                    score_a=sa,
                    score_b=sb,
                    winner=_winner_of(sa, sb),
                )
            )
        return rewards

    def _aggregate(self, per_axis: list[PerAxisReward]) -> tuple[Winner, float]:
        vote_a = sum(self._weight(r.axis) for r in per_axis if r.winner == "a")
        vote_b = sum(self._weight(r.axis) for r in per_axis if r.winner == "b")
        return _winner_of(vote_a, vote_b), abs(vote_a - vote_b)

    def compare(
        self,
        a: AgentTrace,
        b: AgentTrace,
        *,
        solved_a: bool = False,
        solved_b: bool = False,
        diff_a: DiffBundle | None = None,
        diff_b: DiffBundle | None = None,
    ) -> TrajectoryComparison:
        """Compare two trajectories and return a relative preference."""
        ctx_a = AxisContext(solved=solved_a, diff=diff_a)
        ctx_b = AxisContext(solved=solved_b, diff=diff_b)
        per_axis = self.score_axes(a, b, ctx_a, ctx_b)
        overall, margin = self._aggregate(per_axis)
        return TrajectoryComparison(
            overall_winner=overall, per_axis=per_axis, margin=margin
        )

    def cross_judge_audit(self, comparison: TrajectoryComparison) -> CrossJudgeAudit:
        """Fraction of axes whose winner agrees with the overall winner.

        Tie axes (no opinion) are counted as dissenting from a decisive overall
        verdict. When the overall verdict is itself a tie, agreement is the
        fraction of axes that are also ties.
        """
        axes = comparison.per_axis
        if not axes:
            return CrossJudgeAudit(axes_agreement=0.0, dissenting_axes=[])
        agree = sum(1 for r in axes if r.winner == comparison.overall_winner)
        dissenting = [r.axis for r in axes if r.winner != comparison.overall_winner]
        return CrossJudgeAudit(
            axes_agreement=agree / len(axes), dissenting_axes=dissenting
        )

    def reward_sensitivity(
        self,
        a: AgentTrace,
        b: AgentTrace,
        **ctx: object,
    ) -> RewardSensitivityReport:
        """Leave-one-axis-out influence of each axis on the overall winner.

        For each axis, a clone of the judge that omits that axis re-runs the
        comparison. An axis's influence is ``1.0`` if dropping it flips the
        overall winner, else the relative shrink in the decision margin.
        ``ctx`` accepts the same keyword arguments as :meth:`compare`.
        """
        base = self.compare(a, b, **ctx)  # type: ignore[arg-type]
        base_margin = base.margin or 1.0
        influence: dict[str, float] = {}
        for name in self.axes:
            reduced = RelativeTrajectoryJudge(
                weights=self.weights,
                axes={k: v for k, v in self.axes.items() if k != name},
            )
            sub = reduced.compare(a, b, **ctx)  # type: ignore[arg-type]
            if sub.overall_winner != base.overall_winner:
                influence[name] = 1.0
            else:
                drop = max(0.0, base.margin - sub.margin)
                influence[name] = drop / base_margin
        return RewardSensitivityReport(influence=influence)

    def to_preference(
        self,
        comparison: TrajectoryComparison,
        features_a: dict[str, float],
        features_b: dict[str, float],
        *,
        task_id: str = "trajectory-judge",
    ) -> Preference | None:
        """Convert a comparison into a pairwise :class:`Preference`.

        Returns ``None`` when the overall verdict is a tie (no preference).
        """
        if comparison.overall_winner == "a":
            winner, loser = features_a, features_b
        elif comparison.overall_winner == "b":
            winner, loser = features_b, features_a
        else:
            return None
        return Preference(
            task_id=task_id, winner_features=winner, loser_features=loser
        )


def default_trajectory_pair() -> tuple[AgentTrace, AgentTrace]:
    """Two synthetic traces where A is clearly better than B.

    A solves the task minimally, adds a test and activates the harness; B fails,
    bloats the diff, deletes a test and barely uses the harness. Useful for
    tests and artifacts.
    """
    a = AgentTrace(
        attempt_id="traj-a",
        adapter_name="harness",
        is_harness=True,
        status="ok",
        tool_calls=6,
        file_reads=3,
        file_writes=["src/feature.py", "tests/test_feature.py"],
        commands=2,
        changed_files=["src/feature.py", "tests/test_feature.py"],
        diff_lines=24,
        estimated_cost_usd=0.04,
        error=None,
    )
    b = AgentTrace(
        attempt_id="traj-b",
        adapter_name="harness",
        is_harness=True,
        status="error",
        tool_calls=1,
        file_reads=0,
        file_writes=["src/feature.py"],
        commands=0,
        changed_files=["src/feature.py", "tests/test_feature.py"],
        diff_lines=180,
        estimated_cost_usd=0.21,
        error="assertion failed",
    )
    return a, b


def default_pair_context() -> tuple[AxisContext, AxisContext]:
    """Contexts (solved flags + diffs) matching :func:`default_trajectory_pair`.

    Diff A adds a test; diff B deletes one (a security red flag).
    """
    diff_a = DiffBundle(
        changed_files=["src/feature.py", "tests/test_feature.py"],
        added_files=["tests/test_feature.py"],
        insertions=24,
        deletions=0,
        unified_diff="+def test_feature():\n+    assert feature() == 1\n",
    )
    diff_b = DiffBundle(
        changed_files=["src/feature.py", "tests/test_feature.py"],
        deleted_files=["tests/test_feature.py"],
        insertions=120,
        deletions=60,
        unified_diff="-def test_feature():\n-    assert feature() == 1\n",
    )
    return (
        AxisContext(solved=True, diff=diff_a),
        AxisContext(solved=False, diff=diff_b),
    )
