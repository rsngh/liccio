"""Capability matrix — empirical performance per routing cell (alpha-7 WS2).

The router and reviewers need an honest, queryable answer to "which agent /
context strategy / verification policy actually performs best for this kind of
task, and how confident are we in that claim?". The :class:`CapabilityMatrix`
aggregates the empirical evidence already produced elsewhere — bakeoff v2
reports, delayed post-merge outcomes, and OPE reports — into one cell per

    (task_type, risk_level, repo_type, agent_class, context_strategy,
     verification_policy)

with the metric columns success_rate, cost, latency, human_review_rate,
post_merge_failure_rate, OPE_estimated_reward, calibration_confidence,
sample_size and last_updated.

The matrix is deliberately conservative about *overclaiming*: a cell whose
``sample_size`` is below :data:`MIN_SAMPLE` is flagged ``low_sample`` and marked
``sufficient_data=False``, and :meth:`CapabilityMatrix.best_for` refuses to
recommend such a cell. This mirrors the round-5 trace-feature aggregation
pattern (``summarize_agent_history``) but keys on the full routing tuple and
carries explicit data-sufficiency flags rather than opaque scalars.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime

from acp.core.time import isoformat, utcnow

# Cells with fewer than this many observations cannot support a confident claim.
MIN_SAMPLE = 5
# Default routing-tuple components when a bakeoff cell doesn't carry them. Cells
# come from objective bakeoffs (a single canonical action arm), so the strategy
# / policy default to the RoutingAction defaults.
DEFAULT_CONTEXT_STRATEGY = "hybrid_keyword_embedding"
DEFAULT_VERIFICATION_POLICY = "standard"
DEFAULT_AGENT_CLASS = "simple_llm"
DEFAULT_REPO_TYPE = "unknown"

# The six fields that identify a cell.
KEY_FIELDS = (
    "task_type",
    "risk_level",
    "repo_type",
    "agent_class",
    "context_strategy",
    "verification_policy",
)


@dataclass
class CapabilityCell:
    """One row of the capability matrix: a routing tuple plus its metrics.

    The first six fields form the cell key. ``sample_size`` drives
    ``sufficient_data`` / the ``low_sample`` flag, so a low-evidence cell can
    never be silently treated as authoritative.
    """

    # --- key ---
    task_type: str
    risk_level: str
    repo_type: str
    agent_class: str
    context_strategy: str
    verification_policy: str
    # --- metric columns ---
    success_rate: float = 0.0
    cost: float = 0.0
    latency: float = 0.0
    human_review_rate: float = 0.0
    post_merge_failure_rate: float = 0.0
    ope_estimated_reward: float | None = None
    calibration_confidence: float = 0.0
    # Harness-benefit metrics (Alpha 12 WS6); None for non-harness cells.
    har: float | None = None  # harness activation rate (tool loop engaged)
    hfr: float | None = None  # harness following rate (read + write + verify)
    pwl: float | None = None  # pass-when-loaded (solved | activated)
    # Measurement-quality columns (Round 12 WS6 v2): separate conclusive task
    # signal from infra noise so a reviewer can see what the success_rate rests on.
    conclusive_sample_size: int = 0
    inconclusive_sample_size: int = 0
    infra_failure_rate: float = 0.0
    cost_per_conclusive_success: float | None = None
    sample_size: int = 0
    # number of post-merge outcomes folded in (denominator for failure rate)
    post_merge_sample_size: int = 0
    last_updated: datetime = field(default_factory=utcnow)
    sufficient_data: bool = False
    flags: list[str] = field(default_factory=list)

    def key(self) -> tuple[str, ...]:
        """The six-field cell identity."""
        return tuple(getattr(self, f) for f in KEY_FIELDS)

    def key_str(self) -> str:
        """Stable string identity (pipe-joined, mirrors RoutingAction.key)."""
        return "|".join(self.key())

    def task_key(self) -> tuple[str, str, str]:
        """The (task_type, risk_level, repo_type) grouping a query targets."""
        return (self.task_type, self.risk_level, self.repo_type)

    def recompute_flags(self) -> None:
        """Refresh ``sufficient_data`` / ``flags`` / calibration from samples.

        ``calibration_confidence`` is a crude monotone function of sample size
        (0 at no data, → 1 with many observations) so a cell with more evidence
        is reported as more trustworthy without ever claiming certainty.
        """
        self.flags = [f for f in self.flags if f not in ("low_sample", "no_post_merge_data")]
        self.sufficient_data = self.sample_size >= MIN_SAMPLE
        if not self.sufficient_data:
            self.flags.append("low_sample")
        if self.post_merge_sample_size == 0:
            self.flags.append("no_post_merge_data")
        self.calibration_confidence = round(
            self.sample_size / (self.sample_size + MIN_SAMPLE), 3
        )

    def to_dict(self) -> dict:
        """JSON-serializable view (``last_updated`` as an ISO string)."""
        d = asdict(self)
        d["last_updated"] = isoformat(self.last_updated)
        return d


def _agent_class(cell: dict) -> str:
    # bakeoff cells carry the adapter name; treat it as the agent class.
    return cell.get("agent_class") or cell.get("adapter") or DEFAULT_AGENT_CLASS


def _task_type(cell: dict) -> str:
    return cell.get("task_type") or cell.get("task") or "unknown"


def _row_inconclusive(cell: dict) -> bool:
    """A run cell that yields no usable capability signal — excluded from
    aggregation. Delegates to the shared WS1 classifier so the matrix, the bakeoff,
    and the live-ingest path apply one rulebook: an attempt is inconclusive iff its
    classified outcome is not conclusive-quality (infra hang, provider error, etc.).

    A timeout that nonetheless SOLVED the task is a conclusive success; a timeout
    with tool activity but no solve is a conclusive task failure — both are kept.
    """
    from acp.evaluation.measurement_hygiene import classify_attempt
    return not classify_attempt(cell).is_conclusive_quality


class CapabilityMatrix:
    """Aggregated empirical capability per routing tuple.

    Build from a bakeoff report (:meth:`from_bakeoff_report`), then optionally
    fold in delayed post-merge outcomes (:meth:`update_from_outcomes`) and OPE
    estimates (:meth:`attach_ope`). Query with :meth:`best_for` (which skips
    low-sample cells) or :meth:`explain` (which ranks cells and surfaces flags).
    """

    def __init__(self) -> None:
        self._cells: dict[tuple[str, ...], CapabilityCell] = {}

    # ------------------------------------------------------------------ build
    @classmethod
    def from_bakeoff_report(
        cls,
        report: dict,
        *,
        repo_type: str = DEFAULT_REPO_TYPE,
        context_strategy: str = DEFAULT_CONTEXT_STRATEGY,
        verification_policy: str = DEFAULT_VERIFICATION_POLICY,
        last_updated: datetime | None = None,
    ) -> CapabilityMatrix:
        """Build cells from a bakeoff v2 report's per-(task, adapter, run) cells.

        Aggregates success_rate / cost / latency / human_review_rate over every
        run cell that shares the same routing tuple, accumulating ``sample_size``
        from the number of contributing run cells.
        """
        ts = last_updated or utcnow()
        matrix = cls()
        groups: dict[tuple[str, ...], list[dict]] = {}
        for raw in report.get("cells", []):
            key: tuple[str, ...] = (
                _task_type(raw),
                raw.get("risk") or raw.get("risk_level") or "medium",
                repo_type,
                _agent_class(raw),
                raw.get("context_strategy") or context_strategy,
                raw.get("verification_policy") or verification_policy,
            )
            groups.setdefault(key, []).append(raw)

        for key, rows in groups.items():
            tt, risk, rtype, aclass, cstrat, vpol = key
            # Exclude timed-out attempts from capability metrics: a wall-clock
            # timeout reflects provider/infra latency, not whether the agent CAN
            # solve the task, so counting it as a failure would poison routing.
            # An all-timeout cell collapses to sample_size 0 -> low-sample -> never
            # recommended (the no-overclaim guarantee), rather than a false 0.0.
            scored = [r for r in rows if not _row_inconclusive(r)]
            n = len(scored)
            denom = n or 1
            cell = CapabilityCell(
                task_type=tt, risk_level=risk, repo_type=rtype,
                agent_class=aclass, context_strategy=cstrat, verification_policy=vpol,
                success_rate=round(sum(1 for r in scored if r.get("success")) / denom, 4),
                cost=round(sum(float(r.get("cost_usd", 0.0)) for r in scored) / denom, 6),
                latency=round(sum(float(r.get("latency_s", 0.0)) for r in scored) / denom, 4),
                human_review_rate=round(
                    sum(1 for r in scored if r.get("human_review_required")) / denom, 4
                ),
                sample_size=n,
                last_updated=ts,
            )
            # Measurement-quality columns (WS6 v2): conclusive vs inconclusive +
            # infra failure rate + cost per conclusive success.
            from acp.evaluation.measurement_hygiene import classify_attempt
            n_succ = sum(1 for r in scored if r.get("success"))
            inconclusive_rows = [r for r in rows if _row_inconclusive(r)]
            infra_rows = [r for r in rows
                          if classify_attempt(r).is_infra and not r.get("success")]
            total = len(rows) or 1
            cell.conclusive_sample_size = n
            cell.inconclusive_sample_size = len(inconclusive_rows)
            cell.infra_failure_rate = round(len(infra_rows) / total, 4)
            if n_succ:
                cell.cost_per_conclusive_success = round(
                    sum(float(r.get("cost_usd", 0.0)) for r in scored) / n_succ, 6)
            # Harness-benefit metrics (WS6) when the cells carry harness signals.
            harness_rows = [r for r in scored if r.get("is_harness")]
            if harness_rows:
                hn = len(harness_rows)
                activated = [r for r in harness_rows if r.get("tool_calls", 0) > 0]
                cell.har = round(len(activated) / hn, 4)
                followed = sum(
                    1 for r in activated
                    if r.get("file_reads", 0) > 0 and r.get("commands", 0) > 0)
                cell.hfr = round(followed / hn, 4)
                cell.pwl = (round(sum(1 for r in activated if r.get("success")) /
                                  len(activated), 4) if activated else 0.0)
            cell.recompute_flags()
            matrix._cells[cell.key()] = cell
        return matrix

    # --------------------------------------------------------------- outcomes
    def update_from_outcomes(
        self,
        outcomes: list,
        *,
        task_keys: dict[str, tuple[str, ...]] | None = None,
        last_updated: datetime | None = None,
    ) -> int:
        """Fold ``PostMergeOutcome``s into ``post_merge_failure_rate``.

        Each outcome is attributed to a cell either by ``task_keys[task_id]``
        (the full six-field key) or, lacking that, applied to every cell — the
        delayed-outcome idea from the round mirrors: an objective outcome that
        only arrives after merge updates the empirical failure rate later. A
        post-merge *failure* is a revert, reopened issue, or follow-up bug.

        Returns the number of (cell, outcome) attributions made.
        """
        ts = last_updated or utcnow()
        task_keys = task_keys or {}
        # accumulate failures + counts per cell
        acc: dict[tuple[str, ...], list[int]] = {}
        attributions = 0
        for o in outcomes:
            failed = bool(
                getattr(o, "reverted", False)
                or getattr(o, "issue_reopened", False)
                or getattr(o, "followup_bug_created", False)
            )
            target = task_keys.get(getattr(o, "task_id", ""))
            targets = [target] if target is not None else list(self._cells)
            for key in targets:
                if key not in self._cells:
                    continue
                f, c = acc.setdefault(key, [0, 0])
                acc[key] = [f + (1 if failed else 0), c + 1]
                attributions += 1

        for key, (failures, count) in acc.items():
            cell = self._cells[key]
            total_f = round(cell.post_merge_failure_rate * cell.post_merge_sample_size) + failures
            cell.post_merge_sample_size += count
            cell.post_merge_failure_rate = round(
                total_f / cell.post_merge_sample_size, 4
            )
            cell.last_updated = ts
            cell.recompute_flags()
        return attributions

    # -------------------------------------------------------------------- ope
    def attach_ope(
        self,
        ope_report: dict,
        *,
        last_updated: datetime | None = None,
    ) -> int:
        """Set ``ope_estimated_reward`` per cell from an OPE report dict.

        The report is expected to map a cell ``key_str()`` (or a
        ``(task_type, risk_level, repo_type, agent_class, context_strategy,
        verification_policy)`` joined by ``|``) to either a scalar reward or a
        ``{"estimate": float}`` mapping. Returns the number of cells updated.
        """
        ts = last_updated or utcnow()
        per_cell = ope_report.get("per_cell", ope_report)
        updated = 0
        for cell in self._cells.values():
            entry = per_cell.get(cell.key_str())
            if entry is None:
                continue
            value = entry.get("estimate") if isinstance(entry, dict) else entry
            if value is None:
                continue
            cell.ope_estimated_reward = round(float(value), 6)
            cell.last_updated = ts
            updated += 1
        return updated

    # ----------------------------------------------------------------- query
    def cells(self) -> list[CapabilityCell]:
        return list(self._cells.values())

    def add_cell(self, cell: CapabilityCell) -> None:
        """Insert/replace a cell by its key (used when merging matrices)."""
        self._cells[cell.key()] = cell

    def _score(self, cell: CapabilityCell) -> float:
        """Ranking score: prefer OPE reward if present, else success minus risk.

        A tiny cost+latency penalty breaks ties so that, among cells with equal
        success/quality, the cheaper and faster one is chosen (the cost-optimal
        route). The penalty is capped well below one quality point so it can never
        override a real success or post-merge-failure difference.
        """
        if cell.ope_estimated_reward is not None:
            base = cell.ope_estimated_reward
        else:
            base = cell.success_rate
        # Bounded tiebreak: saturating, max magnitude < 0.01 so it only orders
        # otherwise-equal cells. cost in $, latency in seconds.
        tiebreak = 0.005 * (cell.cost / (cell.cost + 0.01)) + \
            0.005 * (cell.latency / (cell.latency + 10.0))
        return base - cell.post_merge_failure_rate - tiebreak

    def _matching(self, task_type: str, risk_level: str, repo_type: str
                  ) -> list[CapabilityCell]:
        tk = (task_type, risk_level, repo_type)
        return [c for c in self._cells.values() if c.task_key() == tk]

    def best_for(
        self, task_type: str, risk_level: str, repo_type: str
    ) -> tuple[CapabilityCell | None, str]:
        """Best *sufficiently sampled* cell for a task key, or ``None`` + reason.

        Low-sample cells are never recommended — this is the no-overclaim
        guarantee. Returns ``(cell, reason)``; ``cell`` is ``None`` when no cell
        has enough data.
        """
        candidates = self._matching(task_type, risk_level, repo_type)
        if not candidates:
            return None, "no_matching_cells"
        confident = [c for c in candidates if c.sufficient_data]
        if not confident:
            return None, f"all_{len(candidates)}_candidate_cells_low_sample"
        best = max(confident, key=self._score)
        return best, f"selected_from_{len(confident)}_confident_of_{len(candidates)}"

    def explain(self, task_key: tuple[str, str, str]) -> dict:
        """Ranked cells + flags for a (task_type, risk_level, repo_type) key."""
        task_type, risk_level, repo_type = task_key
        candidates = self._matching(task_type, risk_level, repo_type)
        ranked = sorted(candidates, key=self._score, reverse=True)
        best, reason = self.best_for(task_type, risk_level, repo_type)
        return {
            "task_key": list(task_key),
            "n_cells": len(candidates),
            "selection_reason": reason,
            "best": best.to_dict() if best else None,
            "ranked": [
                {**c.to_dict(), "score": round(self._score(c), 6)} for c in ranked
            ],
        }

    def to_dict(self) -> dict:
        """JSON-serializable view of the whole matrix."""
        return {
            "min_sample": MIN_SAMPLE,
            "columns": [f.name for f in fields(CapabilityCell)],
            "n_cells": len(self._cells),
            "n_sufficient": sum(1 for c in self._cells.values() if c.sufficient_data),
            "cells": [c.to_dict() for c in self._cells.values()],
        }
