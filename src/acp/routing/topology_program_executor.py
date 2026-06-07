"""Executable topology controller (GOALS Alpha 44 P2).

Beyond offline search (Alpha 43): a controller that EXECUTES an escalation program over a task —
cheap_single, then context-richer retries (grep / repo_map), then advisor / best-of-k, then
strict verification, then human review or abstain — stopping as soon as a hidden-verified result
is reached or the budget is exhausted. Safety is enforced as hard invariants. The attempt
function is injected, so the same controller drives live policies or replays pre-collected
arena traces (AutoTTS-style) without new model calls.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ACTIONS = (
    "cheap_single", "retry_with_grep", "retry_with_repo_map", "ask_readonly_advisor",
    "sample_k_candidates", "branch_parallel", "run_strict_verifier", "route_to_human",
    "abstain", "commit_success", "terminate_failure",
)
# default escalation ladder (cheapest first); high-risk inserts a strict verifier before commit
DEFAULT_LADDER = ("cheap_single", "retry_with_grep", "retry_with_repo_map", "ask_readonly_advisor")


@dataclass
class AttemptOutcome:
    solved: bool                 # hidden-test verified
    public_solved: bool
    cost: float
    touched_forbidden: bool = False
    security_relevant: bool = False


@dataclass
class ControllerResult:
    task: str
    solved: bool
    action_path: list[str] = field(default_factory=list)
    total_cost: float = 0.0
    # commit_success | route_to_human | abstain | terminate_failure
    terminal: str = "terminate_failure"
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"task": self.task, "solved": self.solved, "action_path": self.action_path,
                "total_cost": round(self.total_cost, 6), "terminal": self.terminal,
                "safety_notes": self.safety_notes}


# attempt_fn(action, task_id) -> AttemptOutcome (or None if the action is not applicable)
AttemptFn = Callable[[str, str], "AttemptOutcome | None"]


def run_controller(task_id: str, attempt_fn: AttemptFn, *, risk_level: str = "low",
                   budget: float = 0.05,
                   ladder: tuple[str, ...] = DEFAULT_LADDER) -> ControllerResult:
    """Execute the escalation ladder until hidden-verified or budget/ladder exhausted.

    Safety invariants (hard):
      - a high-risk task may NOT commit without running the strict verifier first;
      - a security-relevant verified result may NOT auto-approve on public tests only — it must be
        hidden-verified;
      - a candidate that touched a forbidden file is never committed.
    """
    res = ControllerResult(task=task_id, solved=False)
    high_risk = risk_level in ("high", "critical")
    for action in ladder:
        if res.total_cost > budget:
            res.terminal = "route_to_human"
            res.safety_notes.append(f"budget {budget} exhausted -> human review")
            res.action_path.append("route_to_human")
            return res
        out = attempt_fn(action, task_id)
        if out is None:
            continue
        res.action_path.append(action)
        res.total_cost += out.cost
        if out.touched_forbidden:
            res.safety_notes.append(f"{action}: touched forbidden file -> rejected")
            continue
        if out.solved:
            # hidden-verified. high-risk/security must pass strict verification before commit.
            if high_risk or out.security_relevant:
                strict = attempt_fn("run_strict_verifier", task_id)
                res.action_path.append("run_strict_verifier")
                if strict is not None:
                    res.total_cost += strict.cost
                    if not strict.solved:
                        res.safety_notes.append("strict verifier failed -> not committed")
                        continue
            res.solved = True
            res.terminal = "commit_success"
            res.action_path.append("commit_success")
            return res
    # ladder exhausted without a verified solve
    if high_risk:
        res.terminal = "route_to_human"
        res.safety_notes.append("high-risk unsolved -> human review, never blind auto-approve")
        res.action_path.append("route_to_human")
    else:
        res.terminal = "abstain"
        res.action_path.append("abstain")
    return res
