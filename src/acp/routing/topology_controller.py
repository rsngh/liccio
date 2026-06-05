"""AutoTTS-style topology controller search (Alpha 24 area 3).

AutoTTS reframes test-time scaling as controller synthesis: instead of repeatedly calling
the base model, search over candidate controllers and evaluate them OFFLINE on pre-collected
traces + probe signals. ACP already has topology actions and measurement-trusted traces, so
this is a direct fit: a controller maps task features to a topology plan (which stages to
run/skip), and we score candidate controllers on a trace dataset to find one that is
cheaper at equal-or-better quality than hand rules.

Hard safety constraints (checked before scoring, a controller that violates any is
discarded): security / high-risk tasks NEVER skip strict verification, and ambiguous tasks
route to spec/advisor before implementation. Promotion of a found controller is still
gated by the staged canary elsewhere — this module only proposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

# Topology action space (subset of the routing actions; cost units are relative).
ACTION_COST = {
    "run_planner": 1.0, "run_retrieval": 1.0, "run_reviewer": 1.0,
    "branch_parallel": 2.0, "run_light_verifier": 0.5, "run_strict_verifier": 1.5,
    "consult_advisor": 2.0,
}


@dataclass
class TopologyTrace:
    """A pre-collected attempt: task features + executed actions + observed outcome."""
    task_type: str
    risk: str                         # low | medium | high
    difficulty: str                   # easy | medium | hard
    ambiguous: bool
    success: bool
    required_strict_verify: bool      # this task genuinely needed strict verification


@dataclass
class ControllerParams:
    skip_planner_on_easy: bool = False
    skip_retrieval_on_low_risk: bool = False
    branch_parallel_on_hard: bool = False
    light_verifier_default: bool = True

    def key(self) -> str:
        return (f"sp={int(self.skip_planner_on_easy)},sr={int(self.skip_retrieval_on_low_risk)},"
                f"bp={int(self.branch_parallel_on_hard)},lv={int(self.light_verifier_default)}")


def plan_actions(p: ControllerParams, trace: TopologyTrace) -> list[str]:
    """Deterministic topology plan for a task. Safety rails are NON-negotiable here."""
    actions: list[str] = []
    # Ambiguous tasks must get a spec/advisor pass before implementation.
    if trace.ambiguous:
        actions.append("consult_advisor")
    if not (p.skip_planner_on_easy and trace.difficulty == "easy"):
        actions.append("run_planner")
    if not (p.skip_retrieval_on_low_risk and trace.risk == "low"):
        actions.append("run_retrieval")
    if p.branch_parallel_on_hard and trace.difficulty == "hard":
        actions.append("branch_parallel")
    # Verification: high-risk / strict-required ALWAYS get strict; else a light pass.
    if trace.risk == "high" or trace.required_strict_verify:
        actions.append("run_strict_verifier")
    elif p.light_verifier_default:
        actions.append("run_light_verifier")
    return actions


def safety_violations(p: ControllerParams, traces: list[TopologyTrace]) -> list[str]:
    """Return reasons a controller is unsafe (empty == safe). Checked before scoring."""
    reasons: list[str] = []
    for t in traces:
        plan = plan_actions(p, t)
        if (t.risk == "high" or t.required_strict_verify) and "run_strict_verifier" not in plan:
            reasons.append(f"skipped strict verify on {t.task_type}/{t.risk}")
        if t.ambiguous and "consult_advisor" not in plan:
            reasons.append(f"no spec/advisor on ambiguous {t.task_type}")
    return reasons


@dataclass
class ControllerScore:
    key: str
    est_cost: float
    est_success: float
    safe: bool
    violations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def score_controller(p: ControllerParams, traces: list[TopologyTrace]) -> ControllerScore:
    """Offline estimate of a controller's cost and success on the trace dataset.

    Cost = mean plan cost. Success uses a conservative direct estimate: a trace's observed
    success is credited only if the controller's plan still runs the verification the task
    needed (skipping required verification forfeits the credit — a bad-merge risk).
    """
    violations = safety_violations(p, traces)
    if not traces:
        return ControllerScore(p.key(), 0.0, 0.0, not violations, violations)
    total_cost = 0.0
    credited = 0
    for t in traces:
        plan = plan_actions(p, t)
        total_cost += sum(ACTION_COST[a] for a in plan)
        verified_ok = (not (t.risk == "high" or t.required_strict_verify)
                       or "run_strict_verifier" in plan)
        if t.success and verified_ok:
            credited += 1
    return ControllerScore(
        key=p.key(), est_cost=round(total_cost / len(traces), 4),
        est_success=round(credited / len(traces), 4), safe=not violations,
        violations=violations)


def _grid() -> list[ControllerParams]:
    bools = [False, True]
    return [ControllerParams(sp, sr, bp, lv)
            for sp, sr, bp, lv in product(bools, bools, bools, bools)]


@dataclass
class ControllerSearchResult:
    baseline: ControllerScore
    best: ControllerScore
    n_candidates: int
    n_safe: int
    improved: bool                     # best is cheaper at >= baseline success
    all_scores: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"baseline": self.baseline.to_dict(), "best": self.best.to_dict(),
                "n_candidates": self.n_candidates, "n_safe": self.n_safe,
                "improved": self.improved,
                "all_scores": [s.to_dict() for s in self.all_scores]}


def search_controllers(traces: list[TopologyTrace], *,
                       baseline: ControllerParams | None = None) -> ControllerSearchResult:
    """Grid-search controllers; among SAFE ones pick the cheapest at >= baseline success."""
    base = baseline or ControllerParams()  # hand-rule default: run everything, light verify
    base_score = score_controller(base, traces)
    scores = [score_controller(p, traces) for p in _grid()]
    safe = [s for s in scores if s.safe]
    eligible = [s for s in safe if s.est_success >= base_score.est_success - 1e-9]
    best = min(eligible, key=lambda s: (s.est_cost, -s.est_success)) if eligible else base_score
    improved = best.est_cost < base_score.est_cost - 1e-9 \
        and best.est_success >= base_score.est_success - 1e-9
    return ControllerSearchResult(
        baseline=base_score, best=best, n_candidates=len(scores), n_safe=len(safe),
        improved=improved, all_scores=scores)
