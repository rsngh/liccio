"""Best-of-k v2 comparator tests (GOALS Alpha 43 P3)."""

from __future__ import annotations

from acp.evaluation.comparator_strength import (
    Candidate,
    early_stop_savings,
    select_best,
)


def test_rejects_public_pass_hidden_fail() -> None:
    cands = [
        Candidate("a", public_pass=True, hidden_pass=False, diff_lines=5),   # over-fit -> reject
        Candidate("b", public_pass=True, hidden_pass=True, diff_lines=8),
    ]
    r = select_best(cands)
    assert r.selected == "b" and r.reject_reasons["a"] == "public_pass_hidden_fail"


def test_prefers_minimal_verified_patch() -> None:
    cands = [
        Candidate("big", public_pass=True, hidden_pass=True, diff_lines=40),
        Candidate("small", public_pass=True, hidden_pass=True, diff_lines=6),
    ]
    assert select_best(cands).selected == "small"


def test_rejects_forbidden_and_gamed() -> None:
    cands = [
        Candidate("f", public_pass=True, hidden_pass=True, diff_lines=3,
                  forbidden_file_touched=True),
        Candidate("g", public_pass=True, hidden_pass=True, diff_lines=3,
                  test_gaming_suspected=True),
        Candidate("ok", public_pass=True, hidden_pass=True, diff_lines=9),
    ]
    r = select_best(cands)
    assert r.selected == "ok"
    assert r.reject_reasons["f"] == "forbidden_file_touched"
    assert r.reject_reasons["g"] == "test_gaming_suspected"


def test_no_verified_candidate_returns_none() -> None:
    cands = [Candidate("a", public_pass=True, hidden_pass=False, diff_lines=5)]
    r = select_best(cands)
    assert r.selected is None and not r.selected_verified


def test_early_stop_saves_cost() -> None:
    cands = [
        Candidate("a", public_pass=True, hidden_pass=True, diff_lines=5, cost=0.002),
        Candidate("b", public_pass=True, hidden_pass=True, diff_lines=5, cost=0.002),
        Candidate("c", public_pass=True, hidden_pass=True, diff_lines=5, cost=0.002),
    ]
    s = early_stop_savings(cands)
    assert s["early_stopped"] and s["candidates_avoided"] == 2 and s["cost_saved"] == 0.004
