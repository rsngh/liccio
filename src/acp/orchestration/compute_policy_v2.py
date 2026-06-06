"""Compute escalation policy v2 (Alpha 38): variance vs systematic, full arm set.

v1 chose among cheap_single/best_of_k/advisor/frontier from reliability. v2 encodes the live
finding that best-of-k only helps VARIANCE failures (the model is sometimes right) and does
NOTHING for SYSTEMATIC failures (always writes the wrong logic) — those need advisor/frontier.
It also adds the evidence-gate arms (ask_for_spec / abstain) and a frontier+verifier arm, and
explains every escalation with its marginal value.

Arms: cheap_single, best_of_k, cheap_plus_advisor, frontier_single, frontier_plus_verifier,
human_escalation, ask_for_spec, abstain.
"""

from __future__ import annotations

from dataclasses import dataclass

ARMS_V2 = ("cheap_single", "best_of_k", "cheap_plus_advisor", "frontier_single",
           "frontier_plus_verifier", "human_escalation", "ask_for_spec", "abstain")
FAILURE_MODES = ("none", "variance", "systematic", "unknown")


@dataclass
class ComputeContextV2:
    single_shot_reliability: float = 1.0
    best_of_k_lift: float | None = None     # measured lift of best-of-k over single shot
    risk: str = "low"                        # low | medium | high
    value: float = 0.5
    evidence_sufficient: bool = True
    spec_ambiguous: bool = False

    def failure_mode(self) -> str:
        if self.single_shot_reliability >= 0.9:
            return "none"
        if self.best_of_k_lift is None:
            return "unknown"
        if self.best_of_k_lift > 0.05:
            return "variance"        # best-of-k recovers it -> stochastic
        return "systematic"          # best-of-k can't help -> capability gap


@dataclass
class ComputeDecisionV2:
    arm: str
    failure_mode: str
    reason: str
    escalated: bool

    def __post_init__(self) -> None:
        if self.arm not in ARMS_V2:
            raise ValueError(f"unknown arm {self.arm}")

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def choose_arm_v2(ctx: ComputeContextV2) -> ComputeDecisionV2:
    """Pick a compute arm from reliability + failure mode + evidence/risk."""
    fm = ctx.failure_mode()
    # 1. evidence gates first — don't spend compute on an under-specified/under-evidenced task
    if ctx.spec_ambiguous:
        return ComputeDecisionV2("ask_for_spec", fm, "ambiguous spec -> get a spec first",
                                 False)
    if not ctx.evidence_sufficient:
        arm = "ask_for_spec" if ctx.risk == "high" else "abstain"
        return ComputeDecisionV2(arm, fm, "insufficient evidence -> do not guess", False)
    # 2. high single-shot reliability -> no escalation
    if fm == "none":
        return ComputeDecisionV2("cheap_single", fm, "high reliability -> no escalation",
                                 False)
    # 3. variance failure -> best-of-k buys solve rate cheaply
    if fm == "variance":
        return ComputeDecisionV2("best_of_k", fm,
                                 f"variance failure (best-of-k lift {ctx.best_of_k_lift}) "
                                 f"-> sample k + verify", True)
    # 4. systematic failure -> sampling won't help; escalate to advisor/frontier
    if fm in ("systematic", "unknown"):
        if ctx.risk == "high":
            return ComputeDecisionV2("frontier_plus_verifier", fm,
                                     "systematic + high risk -> frontier with verification",
                                     True)
        return ComputeDecisionV2("cheap_plus_advisor", fm,
                                 "systematic failure -> advisor diagnosis + cheap retry", True)
    return ComputeDecisionV2("cheap_single", fm, "default", False)


@dataclass
class _ArmLedger:
    solved: int = 0
    n: int = 0
    cost: float = 0.0


class ComputeSpendLedgerV2:
    """Per-arm spend/solve ledger -> marginal value report vs the cheap baseline."""

    def __init__(self) -> None:
        self._arms: dict[str, _ArmLedger] = {}

    def record(self, arm: str, *, solved: bool, cost: float) -> None:
        if arm not in ARMS_V2:
            raise ValueError(f"unknown arm {arm}")
        a = self._arms.setdefault(arm, _ArmLedger())
        a.solved += int(solved)
        a.n += 1
        a.cost += cost

    def marginal_value_report(self, baseline: str = "cheap_single") -> dict:
        b = self._arms.get(baseline)
        base_rate = (b.solved / b.n) if b and b.n else 0.0
        base_cost = (b.cost / b.n) if b and b.n else 0.0
        rows = []
        for arm, a in self._arms.items():
            if not a.n:
                continue
            rate = a.solved / a.n
            cost = a.cost / a.n
            lift = round(rate - base_rate, 4)
            extra = round(cost - base_cost, 6)
            vpd = (round(lift / extra, 4) if extra > 1e-9
                   else (float("inf") if lift > 0 else 0.0))
            rows.append({"arm": arm, "solve_rate": round(rate, 4),
                         "mean_cost": round(cost, 6), "solve_lift": lift,
                         "extra_cost": extra, "value_per_dollar": vpd,
                         "marginal_value_positive": lift > 0 and (extra <= 0 or vpd > 0)})
        return {"experiment": "marginal_value_report", "baseline": baseline,
                "rows": sorted(rows, key=lambda r: r["solve_rate"], reverse=True)}
