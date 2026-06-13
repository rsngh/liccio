"""P12 W2: the referee-as-selector ranking over a pooled best-of-k (no LLM, no I/O)."""

from __future__ import annotations

from evals.issue_replay.ladder_live import _select_best

from acp.verification.repair_battery import BatteryScore


def _score(cid: str, *, score: float, disc: float, guard: float, accept_ok: bool) -> BatteryScore:
    # accept() needs valid + public_pass + >=2 surviving discriminating + disc>=0.8 + guard>=0.9
    return BatteryScore(candidate_id=cid, score=score, public_pass=True, adversarial_high=False,
                        n_discrim_surviving=4, n_discrim_passed=4 if accept_ok else 1,
                        n_guard_surviving=2, n_guard_passed=2,
                        disc_frac=disc, guard_frac=guard, battery_valid=True)


def test_select_prefers_referee_acceptable_candidate() -> None:
    scores = {
        "c0": _score("c0", score=0.99, disc=0.5, guard=1.0, accept_ok=False),  # high score, not ok
        "c1": _score("c1", score=0.80, disc=1.0, guard=1.0, accept_ok=True),   # acceptable
        "c2": _score("c2", score=0.60, disc=0.3, guard=0.8, accept_ok=False),
    }
    assert scores["c1"].accept() and not scores["c0"].accept()
    assert _select_best(scores) == "c1"          # acceptance dominates raw score


def test_select_breaks_ties_by_disc_times_guard_then_score() -> None:
    # none acceptable -> rank by weighted disc*guard, then score
    scores = {
        "c0": _score("c0", score=0.90, disc=0.5, guard=0.6, accept_ok=False),  # 0.30
        "c1": _score("c1", score=0.50, disc=0.7, guard=0.9, accept_ok=False),  # 0.63 best product
        "c2": _score("c2", score=0.95, disc=0.4, guard=0.7, accept_ok=False),  # 0.28
    }
    assert not any(s.accept() for s in scores.values())
    assert _select_best(scores) == "c1"
