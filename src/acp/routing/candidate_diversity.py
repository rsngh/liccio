"""Candidate diversity for best-of-k v3 (GOALS Alpha 44 P4).

Alpha 43 showed naive best-of-k (same prompt twice) added no quality. v3 samples DIVERSE arms
(different context strategy / prompt / repair path) so the proof-based comparator has genuinely
different candidates to select from. This module scores a candidate set's diversity and computes
the marginal value of adding each extra (diverse) candidate from observed solve outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass

DIVERSITY_ARMS = (
    "grep_context", "repo_map_context", "memory_context", "test_first_prompt",
    "minimal_patch_prompt", "security_hardened_prompt", "advisor_seeded_prompt",
    "cheap_then_strong_repair",
)


@dataclass
class DiversityCandidate:
    arm: str
    solved: bool                 # hidden-verified
    cost: float


def diversity_score(candidates: list[DiversityCandidate]) -> float:
    """Fraction of distinct arms among the candidates (1.0 = all different)."""
    if not candidates:
        return 0.0
    return round(len({c.arm for c in candidates}) / len(candidates), 4)


def best_of_k_outcome(candidates: list[DiversityCandidate]) -> dict:
    """A diverse set solves iff ANY arm is hidden-verified; report waste + marginal value."""
    solved = any(c.solved for c in candidates)
    k = len(candidates)
    n_solving = sum(1 for c in candidates if c.solved)
    total_cost = round(sum(c.cost for c in candidates), 6)
    # marginal value of each extra candidate beyond the first: did it newly solve?
    first_solved = candidates[0].solved if candidates else False
    rescued_by_diversity = solved and not first_solved
    return {
        "k": k, "solved": solved, "diversity_score": diversity_score(candidates),
        "n_solving_candidates": n_solving,
        "waste_rate": round((k - (1 if solved else 0)) / k, 4) if k else 0.0,
        "rescued_by_diversity": rescued_by_diversity,
        "total_cost": total_cost,
        "cost_per_verified": round(total_cost, 6) if solved else None,
    }


def compare_naive_vs_diverse(naive: list[DiversityCandidate],
                             diverse: list[DiversityCandidate]) -> dict:
    """Does diversity beat naive same-arm sampling on verified success?"""
    n_out = best_of_k_outcome(naive)
    d_out = best_of_k_outcome(diverse)
    return {"naive": n_out, "diverse": d_out,
            "diversity_improves_success": d_out["solved"] and not n_out["solved"],
            "diversity_score_naive": n_out["diversity_score"],
            "diversity_score_diverse": d_out["diversity_score"]}
