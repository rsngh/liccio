"""Claim registry (GOALS Alpha 43 P13).

Every headline claim ACP makes maps to the artifact(s) that must exist, be fresh, be the right
evidence tier, and be uncontaminated to support it. The claim checker enforces this so docs can
never overclaim stale, fixture-only, or contaminated evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    requires: tuple[str, ...]          # artifact paths (relative to repo root) that must support it
    tier: str = "live"                 # required evidence tier: live | fixture | any
    forbid_contaminated: bool = True
    # an optional (field, expected) the artifact must satisfy, e.g. ("repo_map_helps", True)
    must_assert: tuple[tuple[str, object], ...] = field(default_factory=tuple)


# The claims ACP is allowed to make, each bound to fresh committed evidence.
CLAIMS: list[Claim] = [
    Claim("repo_map_cross_file",
          "repo_map context improves cross-file coding tasks",
          requires=("reports/live/repo_map_ab.json", "evals/reports/repo_map_coverage.json"),
          tier="any", must_assert=(("repo_map_helps", True),)),
    Claim("advisor_improves",
          "advisor escalation improves verified success",
          requires=("reports/advisor_ope.json",),
          tier="any", must_assert=(("passes_acceptance", True),)),
    Claim("best_of_k_value",
          "best-of-k is cost-competitive (cheaper than the strong single agent)",
          requires=("reports/best_of_k_comparator.json",),
          tier="any", must_assert=(("passes_acceptance", True),)),
    Claim("context_routed_by_ope",
          "context strategy is routed by OPE, not hardcoded",
          requires=("reports/context_strategy_ope.json",), tier="any"),
    Claim("finops_promotion",
          "FinOps promotes a router only on a Pareto cost/quality improvement",
          requires=("reports/finops_cost_per_verified_success.json",), tier="any"),
    Claim("memory_helps_repeated",
          "memory improves first-attempt success on repeated-pattern tasks",
          requires=("reports/memory_aging_smoke.json",),
          tier="any", must_assert=(("memory_helps", True),)),
    Claim("metarouter_scaled",
          "the MetaRouter Arena is proven at scale (>=300 conclusive cells)",
          requires=("reports/metarouter_arena_scaled.json",),
          tier="any", must_assert=(("all_gates_pass", True),)),
    Claim("provider_availability",
          "unavailable providers are discoverable but not counted as capability failures",
          requires=("reports/vendor_native_live_gate.json",),
          tier="any", must_assert=(("availability_separated_from_capability", True),)),
]
