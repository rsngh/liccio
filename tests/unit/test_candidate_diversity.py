"""Best-of-k v3 candidate diversity tests (GOALS Alpha 44 P4)."""

from __future__ import annotations

from acp.routing.candidate_diversity import (
    DiversityCandidate,
    best_of_k_outcome,
    compare_naive_vs_diverse,
    diversity_score,
)


def test_diversity_score() -> None:
    assert diversity_score([DiversityCandidate("a", False, 0.002)] * 3) == round(1/3, 4)
    assert diversity_score([DiversityCandidate("a", False, 0.002),
                            DiversityCandidate("b", False, 0.002)]) == 1.0


def test_diverse_set_rescues_where_naive_fails() -> None:
    naive = [DiversityCandidate("minimal_patch_prompt", False, 0.002) for _ in range(3)]
    diverse = [DiversityCandidate("minimal_patch_prompt", False, 0.002),
               DiversityCandidate("repo_map_context", True, 0.003),
               DiversityCandidate("grep_context", True, 0.003)]
    cmp = compare_naive_vs_diverse(naive, diverse)
    assert cmp["diversity_improves_success"]
    assert cmp["diverse"]["rescued_by_diversity"]
    assert cmp["diversity_score_diverse"] == 1.0


def test_waste_rate_and_cost() -> None:
    cands = [DiversityCandidate("a", True, 0.002), DiversityCandidate("b", True, 0.003)]
    out = best_of_k_outcome(cands)
    assert out["solved"] and out["waste_rate"] == 0.5   # 1 used of 2
    assert out["cost_per_verified"] == 0.005


def test_no_solve_returns_none_cost() -> None:
    cands = [DiversityCandidate("a", False, 0.002)]
    assert best_of_k_outcome(cands)["cost_per_verified"] is None
