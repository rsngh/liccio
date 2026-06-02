"""Full run-graph schema (round-2 Block B).

A single typed envelope that holds every entity produced by a run, so a run can
be reconstructed from DB + artifact store alone and validated as a unit.
"""

from __future__ import annotations

from typing import Any

from acp.schemas.base import ACPModel


class RunGraph(ACPModel):
    state: dict[str, Any]
    task: dict[str, Any] | None = None
    viability: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    context_pack: dict[str, Any] | None = None
    verification_plan: dict[str, Any] | None = None
    routing_decision: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []
    diffs: list[dict[str, Any]] = []
    command_runs: list[dict[str, Any]] = []
    verification_runs: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    evaluation: dict[str, Any] | None = None
    weak_labels: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    human_labels: list[dict[str, Any]] = []
    reward_events: list[dict[str, Any]] = []
    post_merge_outcomes: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []
    agent_traces: list[dict[str, Any]] = []

    def referenced_ids(self) -> set[str]:
        """All entity ids present in the graph (for id-resolution checks)."""
        ids: set[str] = set()
        for group in (self.attempts, self.diffs, self.command_runs, self.verification_runs,
                      self.evidence, self.weak_labels, self.review_items, self.human_labels,
                      self.reward_events, self.post_merge_outcomes, self.spans,
                      self.audit_events):
            for row in group:
                if "id" in row:
                    ids.add(row["id"])
        for obj in (self.task, self.snapshot, self.context_pack, self.verification_plan,
                    self.routing_decision, self.evaluation):
            if obj and "id" in obj:
                ids.add(obj["id"])
        return ids
