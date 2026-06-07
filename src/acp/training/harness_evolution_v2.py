"""Harness evolution as guarded PRs (GOALS Alpha 44 P7).

Close the loop from conclusive failures to PROPOSED, governed harness patches (Meta-Harness /
Agentic Harness Engineering): cluster failed traces by mode, propose a bounded patch to an
editable component (with a self-declared expected effect + rollback metadata), then gate it
through static/security scan, a regression suite, a negative-transfer suite, and a canary. A
patch is promoted ONLY with a significant canary lift and no negative transfer — and never via a
direct protected-branch write. Deterministic; the canary/regression signals are injected.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

EDITABLE_COMPONENTS = (
    "tool_schema", "finish_discipline", "test_running_discipline", "grep_presentation",
    "repo_map_presentation", "memory_snippet_presentation", "advisor_trigger",
    "best_of_k_diversity_prompts", "budget_policy", "error_nudge_handling",
)


def _get(c: Any, k: str, d=None):
    return c.get(k, d) if isinstance(c, dict) else getattr(c, k, d)


@dataclass
class FailureCluster:
    mode: str                # e.g. "grep_router:security_fix"
    n: int
    example_tasks: list[str] = field(default_factory=list)


def cluster_failures(cells: list[Any], *, min_size: int = 2) -> list[FailureCluster]:
    """Group conclusive failures by (policy/component : task_type) failure mode."""
    groups: dict[str, list[str]] = defaultdict(list)
    for c in cells:
        if _get(c, "conclusive", True) and not _get(c, "solved", False):
            mode = f"{_get(c, 'policy', 'agent')}:{_get(c, 'task_type', 'unknown')}"
            groups[mode].append(str(_get(c, "task", "?")))
    out = [FailureCluster(m, len(v), v[:5]) for m, v in groups.items() if len(v) >= min_size]
    return sorted(out, key=lambda c: -c.n)


@dataclass
class HarnessPatchProposal:
    component: str
    cluster_mode: str
    rationale: str
    expected_effect: str
    diff_summary: str
    rollback: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"component": self.component, "cluster_mode": self.cluster_mode,
                "rationale": self.rationale, "expected_effect": self.expected_effect,
                "diff_summary": self.diff_summary, "rollback": self.rollback}


# heuristic mapping from a failure mode to the harness component most likely responsible
_MODE_TO_COMPONENT = {
    "security": "finish_discipline", "underspec": "advisor_trigger",
    "cross_file": "repo_map_presentation", "memrep": "memory_snippet_presentation",
}


def propose_patch(cluster: FailureCluster) -> HarnessPatchProposal:
    comp = next((c for k, c in _MODE_TO_COMPONENT.items() if k in cluster.mode),
                "test_running_discipline")
    return HarnessPatchProposal(
        component=comp, cluster_mode=cluster.mode,
        rationale=f"{cluster.n} conclusive failures clustered under {cluster.mode}",
        expected_effect=f"raise pass-when-loaded on the {cluster.mode} bucket",
        diff_summary=f"adjust {comp} for {cluster.mode}",
        rollback={"action": "revert component", "component": comp,
                  "restore": "previous harness version"})


@dataclass
class GuardedPRResult:
    proposal: dict
    static_scan_passed: bool
    regression_passed: bool
    negative_transfer: bool
    canary_lift: float
    promoted: bool
    decision: str

    def to_dict(self) -> dict:
        return {**{"proposal": self.proposal}, "static_scan_passed": self.static_scan_passed,
                "regression_passed": self.regression_passed,
                "negative_transfer": self.negative_transfer, "canary_lift": self.canary_lift,
                "promoted": self.promoted, "decision": self.decision,
                "protected_branch_write": False}


def evaluate_proposal(proposal: HarnessPatchProposal, *, static_ok: bool, regression_ok: bool,
                      negative_transfer: bool, canary_lift: float,
                      min_lift: float = 0.05) -> GuardedPRResult:
    """Promote only with a clean scan + regression, NO negative transfer, and a significant lift."""
    if not static_ok:
        decision, promoted = "rejected: static/security scan failed", False
    elif not regression_ok:
        decision, promoted = "rejected: regression suite failed", False
    elif negative_transfer:
        decision, promoted = "rejected: negative transfer on other buckets", False
    elif canary_lift < min_lift:
        decision, promoted = f"rejected: canary lift {canary_lift} < {min_lift}", False
    else:
        decision, promoted = f"promoted via guarded PR (canary lift {canary_lift})", True
    return GuardedPRResult(proposal.to_dict(), static_ok, regression_ok, negative_transfer,
                           canary_lift, promoted, decision)
