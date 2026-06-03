"""Pareto routing live configuration (Alpha 11, WS2).

Maps task types (and risk levels) to multi-objective weight *profiles* so an
operator can declare routing objectives per task class without code changes:

    profiles:
      docs: cost_saver
      bugfix: balanced
      ci_fix: latency_min
      security_fix: risk_min
      incident: success_max

`ParetoRoutingConfig.resolve` returns the `ParetoWeightProfile` for a task,
applying a safety override (high/critical risk never routes below `risk_min`'s
risk weight) and falling back to a default profile for unmapped task types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import RiskLevel
from acp.routing.pareto_policy import PROFILES, ParetoWeightProfile

_DEFAULT_MAP: dict[str, str] = {
    "docs": "cost_saver",
    "dependency_update": "cost_saver",
    "bugfix": "balanced",
    "feature": "balanced",
    "refactor": "balanced",
    "test_generation": "balanced",
    "ci_fix": "latency_min",
    "security_fix": "risk_min",
    "migration": "risk_min",
}


@dataclass
class ParetoRoutingConfig:
    profile_by_task_type: dict[str, str] = field(
        default_factory=lambda: dict(_DEFAULT_MAP))
    default_profile: str = "balanced"

    @classmethod
    def from_dict(cls, data: dict) -> ParetoRoutingConfig:
        profiles = dict(data.get("profiles", {}))
        for name in profiles.values():
            if name not in PROFILES:
                raise ValueError(f"unknown Pareto profile {name!r}; "
                                 f"valid: {sorted(PROFILES)}")
        return cls(profile_by_task_type={**_DEFAULT_MAP, **profiles},
                   default_profile=data.get("default", "balanced"))

    def profile_name(self, task_type: str, risk_level: str = "medium") -> str:
        name = self.profile_by_task_type.get(task_type, self.default_profile)
        # Safety override: high/critical risk is never routed below risk_min.
        try:
            if RiskLevel(risk_level).rank >= RiskLevel.HIGH.rank:
                name = "risk_min"
        except ValueError:
            pass
        return name

    def resolve(self, task_type: str, risk_level: str = "medium") -> ParetoWeightProfile:
        return PROFILES[self.profile_name(task_type, risk_level)]
