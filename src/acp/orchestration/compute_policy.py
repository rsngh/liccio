"""Compute-escalation policy + spend ledger (Alpha 29).

Turns expensive compute (best-of-k, advisor, frontier) into a learned, auditable policy:
ACP escalates beyond a cheap single shot ONLY where the marginal value is positive. The
policy reads measured single-shot reliability + task value/risk to pick an arm, and a spend
ledger records (arm, cost, solved) so marginal value (solve lift per extra dollar over the
cheap baseline) is evidence, not assumption. Every choice carries a rationale for the dossier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ARMS = ("cheap_single", "cheap_best_of_k", "cheap_advisor", "frontier_single")
BASELINE = "cheap_single"


@dataclass
class ComputeSpendLedger:
    _rows: list = field(default_factory=list)   # list[(arm, cost, solved)]

    def record(self, arm: str, cost: float, solved: bool) -> None:
        if arm not in ARMS:
            raise ValueError(f"unknown arm {arm}")
        self._rows.append((arm, float(cost), bool(solved)))

    def stats(self, arm: str) -> dict:
        rows = [r for r in self._rows if r[0] == arm]
        n = len(rows)
        if not n:
            return {"arm": arm, "n": 0, "solve_rate": 0.0, "mean_cost": 0.0}
        return {"arm": arm, "n": n,
                "solve_rate": round(sum(r[2] for r in rows) / n, 4),
                "mean_cost": round(sum(r[1] for r in rows) / n, 6)}

    def marginal_value(self, arm: str, baseline: str = BASELINE) -> dict:
        """Solve lift and extra cost of ``arm`` over ``baseline`` (value per extra dollar)."""
        a, b = self.stats(arm), self.stats(baseline)
        if a["n"] == 0 or b["n"] == 0:
            return {"arm": arm, "known": False, "solve_lift": None,
                    "extra_cost": None, "value_per_dollar": None, "positive": None}
        lift = round(a["solve_rate"] - b["solve_rate"], 4)
        extra = round(a["mean_cost"] - b["mean_cost"], 6)
        vpd = round(lift / extra, 4) if extra > 1e-9 else (float("inf") if lift > 0 else 0.0)
        return {"arm": arm, "known": True, "solve_lift": lift, "extra_cost": extra,
                "value_per_dollar": vpd, "positive": lift > 0 and (extra <= 0 or vpd > 0)}


@dataclass
class EscalationDecision:
    arm: str
    reason: str
    escalated: bool

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ComputePolicy:
    high_reliability: float = 0.9       # >= -> cheap single shot suffices
    low_reliability: float = 0.5        # < -> needs more than parallel sampling


def choose_arm(*, single_shot_reliability: float, risk: str = "low", value: float = 0.5,
               ledger: ComputeSpendLedger | None = None, policy: ComputePolicy | None = None
               ) -> EscalationDecision:
    """Pick a compute arm. Escalate to an expensive arm only with positive marginal value.

    - high single-shot reliability  -> cheap single shot (no escalation, no waste);
    - medium reliability            -> best-of-k (cheap parallelism + execution verifier);
    - low reliability + high risk/value -> advisor or frontier, BUT only if the ledger shows
      positive marginal value for that arm (unknown value is allowed for high-risk only).
    """
    p = policy or ComputePolicy()

    def _ledger_ok(arm: str) -> bool:
        if ledger is None:
            return risk == "high" or value >= 0.7   # no evidence yet: allow for high stakes
        mv = ledger.marginal_value(arm)
        return mv["positive"] is True or (mv["positive"] is None and risk == "high")

    if single_shot_reliability >= p.high_reliability:
        return EscalationDecision(BASELINE, "high single-shot reliability -> no escalation",
                                  False)
    if single_shot_reliability >= p.low_reliability:
        if _ledger_ok("cheap_best_of_k"):
            return EscalationDecision("cheap_best_of_k",
                                      "medium reliability -> sample k + verify", True)
        return EscalationDecision(BASELINE, "best-of-k marginal value not positive", False)
    # low reliability: parallel sampling alone is unlikely to help -> advisor/frontier
    for arm in ("cheap_advisor", "frontier_single"):
        if _ledger_ok(arm):
            return EscalationDecision(arm,
                                      f"low reliability + stakes -> {arm} (positive value)",
                                      True)
    return EscalationDecision("cheap_best_of_k",
                              "low reliability but no escalation justified -> best-effort", True)


def arms_summary(ledger: ComputeSpendLedger) -> dict:
    """Per-arm stats + marginal value vs the cheap baseline (for the policy dossier)."""
    by_arm: dict[str, dict] = {}
    for arm in ARMS:
        by_arm[arm] = {**ledger.stats(arm), "marginal": ledger.marginal_value(arm)}
    return by_arm
