# ruff: noqa: E501
"""Independent-proof verifier — offline tests (real pytest on tiny fixtures, no network)."""

from __future__ import annotations

from pathlib import Path

from acp.evaluation.comparator_strength import (
    Candidate,
    select_best,
    select_best_online,
)
from acp.verification.independent_proof import generate_checks, proxy_evaluate


def test_generate_checks_no_client_is_empty() -> None:
    g = generate_checks(_spec("rev the string"), client=None)
    assert g.checks == [] and g.cost_usd == 0.0


def test_online_selector_rejects_overfit_and_falls_back() -> None:
    # overfit candidate (public pass, proxy fail) is rejected; minimal proxy-verified chosen
    cs = [Candidate("overfit", public_pass=True, hidden_pass=False, diff_lines=2, proxy_pass=False),
          Candidate("good", public_pass=True, hidden_pass=True, diff_lines=9, proxy_pass=True)]
    r = select_best_online(cs)
    assert r.selected == "good" and r.selected_verified
    assert r.reject_reasons["overfit"] == "public_pass_proxy_fail"
    # when nothing is proxy-verified, fall back to first public-passing (never worse than public-only)
    cs2 = [Candidate("a", public_pass=True, hidden_pass=False, diff_lines=2, proxy_pass=None),
           Candidate("b", public_pass=False, hidden_pass=False, diff_lines=2, proxy_pass=None)]
    assert select_best_online(cs2).selected == "a"


def test_proxy_evaluate_distinguishes_overfit_and_drops_bad_checks(tmp_path: Path) -> None:
    spec = _spec("rev(s) reverses the string")
    correct = _ws(tmp_path / "correct", "def rev(s):\n    return s[::-1]\n")
    overfit = _ws(tmp_path / "overfit", "def rev(s):\n    return s\n")  # passes 1-char, fails real
    good_check = "from r import rev\n\ndef test_g():\n    assert rev('ab') == 'ba'\n"
    bad_check = "from r import rev\n\ndef test_b():\n    assert rev('x') == 'WRONG'\n"  # wrong expectation
    cands = [{"id": "correct", "workspace": correct, "public_pass": True, "diff": ""},
             {"id": "overfit", "workspace": overfit, "public_pass": True, "diff": ""}]
    verdicts = proxy_evaluate(spec, cands, tmp_path / "work", checks=[good_check, bad_check])
    # the bad check (both/most fail) is consensus-dropped; the good check survives
    assert verdicts["correct"].n_checks_surviving == 1
    # correct passes the surviving good check -> proxy_pass; overfit fails it -> proxy_fail
    assert verdicts["correct"].proxy_pass is True
    assert verdicts["overfit"].proxy_pass is False


def test_proxy_matches_oracle_when_perfect() -> None:
    # if proxy_pass == hidden_pass for all candidates, online selection == oracle selection
    cs = [Candidate("x", public_pass=True, hidden_pass=False, diff_lines=2, proxy_pass=False),
          Candidate("y", public_pass=True, hidden_pass=True, diff_lines=4, proxy_pass=True)]
    assert select_best_online(cs).selected == select_best(cs).selected == "y"


def _spec(issue: str):
    class S:
        issue_text = issue
        public_test = "from r import rev\n\ndef test_pub():\n    assert rev('abc') == 'cba'\n"
        module_path = "r.py"
    return S()


def _ws(path: Path, module_src: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "r.py").write_text(module_src)
    (path / "conftest.py").write_text("import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    return path
