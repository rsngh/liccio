# ruff: noqa: E501
"""Max-capability ensemble router — offline tests (mock arms; no network)."""

from __future__ import annotations

from acp.routing.capability_router import Candidate, oracle_capture_rate, solve_ensemble


def _cands():
    # A: correct + proxy-verified; B: overfit (public yes, hidden no, proxy no); C: total fail
    return {
        "A": Candidate("A", public_pass=True, hidden_pass=True, cost=0.01, diff="x"),
        "B": Candidate("B", public_pass=True, hidden_pass=False, cost=0.005, diff="yy"),
        "C": Candidate("C", public_pass=False, hidden_pass=False, cost=0.002, diff=""),
    }


def test_ensemble_selects_verified_and_rejects_overfit() -> None:
    c = _cands()
    proxy = {"A": True, "B": False, "C": False}   # verifier catches the overfit B
    r = solve_ensemble(arms=["C", "B", "A"], run_arm_fn=lambda a: c[a],
                       verify_fn=lambda ran: {x.arm: proxy[x.arm] for x in ran}, budget=1.0)
    assert r.solved and r.selected_arm == "A" and r.any_correct
    assert r.terminal == "proxy_verified" and r.selected_proxy_pass


def test_ensemble_captures_union_a_single_arm_misses() -> None:
    # no single arm solves both tasks, but the union does — and the verifier picks the right one
    def task(good_arm):
        c = {"A": Candidate("A", good_arm == "A", good_arm == "A", 0.01),
             "B": Candidate("B", good_arm == "B", good_arm == "B", 0.01)}
        proxy = {k: v.hidden_pass for k, v in c.items()}   # ideal verifier
        return solve_ensemble(arms=["A", "B"], run_arm_fn=lambda a: c[a],
                              verify_fn=lambda ran: {x.arm: proxy[x.arm] for x in ran}, budget=1.0)
    rs = [task("A"), task("B")]            # arm A solves t1, arm B solves t2
    assert all(r.solved for r in rs)       # ensemble solves both; neither single arm would
    assert oracle_capture_rate(rs)["verifier_capture_rate"] == 1.0


def test_spend_to_budget_stops() -> None:
    c = {"A": Candidate("A", False, False, 0.2), "B": Candidate("B", True, True, 0.2)}
    # budget only affords ~one arm; B (which would solve) is never reached
    r = solve_ensemble(arms=["A", "B"], run_arm_fn=lambda a: c[a],
                       verify_fn=lambda ran: {x.arm: x.hidden_pass for x in ran}, budget=0.1)
    assert r.terminal == "budget_exhausted" and r.n_arms_run == 1 and not r.solved


def test_no_overclaim_when_verifier_blind() -> None:
    # a blind verifier (always False) captures nothing even though an arm was correct
    c = _cands()
    r = solve_ensemble(arms=["A"], run_arm_fn=lambda a: c[a],
                       verify_fn=lambda ran: {x.arm: False for x in ran}, budget=1.0)
    assert r.any_correct and not r.selected_proxy_pass   # ceiling existed; verifier didn't capture it
