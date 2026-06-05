"""Evidence-gap analyzer + experiment planner (Alpha 32 seed).

The review's milestone is *evidence depth*: the architecture is ahead of the evidence. This
module reads the control-plane health snapshot and reports, with severity, where the evidence
is missing or weak — failed production gates, a non-discriminating benchmark, low vendor
activation, no promoted skill, stale report truth — and turns those gaps into a PRIORITIZED
experiment plan ("what should ACP learn next"). It is the seed of the autonomous loop: a
deterministic, auditable read of where to spend the next live budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY = ("info", "low", "medium", "high")


@dataclass
class EvidenceGap:
    dimension: str
    severity: str
    detail: str
    recommended_experiment: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY:
            raise ValueError(f"bad severity {self.severity}")

    def to_dict(self) -> dict:
        return dict(self.__dict__)


# Failed production gate -> (severity, the experiment that would close it).
_GATE_EXPERIMENTS = {
    "docker_live_security_passed": ("high", "acp eval docker-security-live"),
    "vendor_harness_live_passed": ("high", "acp eval vendor-harness-live"),
    "benchmark_baseline_present": ("high", "run_benchmark_baseline_live.py"),
    "measurement_quality_trusted": ("medium", "refresh measurement-quality report"),
    "ope_overlap_sufficient": ("medium", "collect more routing log overlap"),
    "report_truth_consistent": ("high", "acp reports sync-status --strict"),
    "artifact_manifest_valid": ("high", "acp reports validate + regenerate stale artifacts"),
    "harness_availability_ok": ("medium", "harness availability audit"),
    "measurement_not_contaminated": ("medium", "re-measure on a clean conclusive corpus"),
}


def analyze_evidence_gaps(health: dict) -> list:
    """Read a control-plane health dict and return the evidence gaps, most severe first."""
    gaps: list[EvidenceGap] = []
    gates = health.get("production_gates", {})
    for gate, ok in gates.items():
        if ok is False:
            sev, exp = _GATE_EXPERIMENTS.get(gate, ("medium", f"satisfy gate {gate}"))
            gaps.append(EvidenceGap(dimension=gate, severity=sev,
                                    detail=f"production gate {gate} failing",
                                    recommended_experiment=exp))
    bench = health.get("benchmark", {})
    if bench.get("baseline_overall") is not None and not bench.get("discriminating"):
        gaps.append(EvidenceGap(
            dimension="benchmark_discrimination", severity="medium",
            detail="benchmark at ceiling (overall 1.0) -> cannot measure skill lift",
            recommended_experiment="run_hard_best_of_k_live.py (harder tasks)"))
    if bench.get("skill_ab_decision") in (None, "abstain"):
        gaps.append(EvidenceGap(
            dimension="skill_evidence", severity="low",
            detail="no promoted skill with measured lift on this scope",
            recommended_experiment="run_underspecified_skill_ab_live.py"))
    # vendor activation (Alpha 26): low activation -> measurement untrustworthy
    vendor_act = health.get("measurement", {}).get("vendor_activation_rate")
    if vendor_act is not None and vendor_act < 0.8:
        gaps.append(EvidenceGap(
            dimension="vendor_activation", severity="medium",
            detail=f"vendor activation {vendor_act} < 0.8 -> capability reads untrustworthy",
            recommended_experiment="re-run vendor corpus when CLI healthy"))
    order = {s: i for i, s in enumerate(reversed(SEVERITY))}
    return sorted(gaps, key=lambda g: order[g.severity])


@dataclass
class ExperimentPlan:
    n_gaps: int
    by_severity: dict = field(default_factory=dict)
    plan: list = field(default_factory=list)   # ordered list of recommended experiments

    def to_dict(self) -> dict:
        return {"n_gaps": self.n_gaps, "by_severity": self.by_severity, "plan": self.plan}


def plan_experiments(health: dict, *, budget: int | None = None) -> ExperimentPlan:
    """Turn evidence gaps into a prioritized, de-duplicated experiment plan."""
    from collections import Counter
    gaps = analyze_evidence_gaps(health)
    by_sev = dict(Counter(g.severity for g in gaps))
    seen: set = set()
    plan: list[dict] = []
    for g in gaps:
        if g.recommended_experiment in seen:
            continue
        seen.add(g.recommended_experiment)
        plan.append({"experiment": g.recommended_experiment, "for": g.dimension,
                     "severity": g.severity})
    if budget is not None:
        plan = plan[:max(0, budget)]
    return ExperimentPlan(n_gaps=len(gaps), by_severity=by_sev, plan=plan)
