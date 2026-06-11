"""P7 W3: strategy categorization + MCTS node bookkeeping (no LLM calls)."""

from __future__ import annotations

from evals.issue_replay.guided_repair import _maybe_escalate, _Node, _select_final, _uct
from evals.issue_replay.repair_strategies import CATEGORIES, STRATEGIES, categorize, directive

from acp.verification.repair_battery import BatteryScore


def _sc(score: float, *, disc: float, guard: float, adv: bool = False,
        public: bool = True, n_disc: int = 4) -> BatteryScore:
    return BatteryScore(candidate_id="x", score=score, public_pass=public, adversarial_high=adv,
                        n_discrim_surviving=n_disc, n_discrim_passed=int(disc * n_disc),
                        n_guard_surviving=3, n_guard_passed=int(guard * 3),
                        disc_frac=disc, guard_frac=guard, battery_valid=True)


def test_categorize_covers_modes() -> None:
    assert categorize(None) == "no_parse"
    assert categorize(_sc(0.0, disc=1.0, guard=1.0, adv=True)) == "adversarial"
    assert categorize(_sc(0.5, disc=0.8, guard=0.6)) == "guard_regression"
    assert categorize(_sc(0.4, disc=0.0, guard=1.0)) == "discriminating_stuck"
    assert categorize(_sc(0.7, disc=0.5, guard=1.0)) == "wrong_value"
    assert categorize(_sc(0.4, disc=0.0, guard=1.0), "TypeError: bad call") == "exception"
    assert set(STRATEGIES) == set(CATEGORIES)
    for cat in CATEGORIES:
        assert directive(cat, 0) and directive(cat, 7)   # round-robin never IndexErrors


def test_uct_penalizes_failures() -> None:
    parent = _Node(src="p", score=_sc(0.4, disc=0.0, guard=1.0), visits=10)
    good = _Node(src="a", score=_sc(0.8, disc=0.7, guard=1.0), parent=parent, visits=2, value=1.6)
    flaky = _Node(src="b", score=_sc(0.8, disc=0.7, guard=1.0), parent=parent, visits=2, value=1.6,
                  failures=4)
    assert _uct(parent, good) > _uct(parent, flaky)      # failed expansions damp the branch


def test_select_final_prefers_accept_over_raw_score() -> None:
    a = ("srcA", _sc(0.95, disc=0.9, guard=1.0))         # accept() True
    b = ("srcB", _sc(0.97, disc=0.7, guard=1.0))         # higher raw score, accept() False
    assert _select_final([b, a])[0] == "srcA"


def test_maybe_escalate_only_on_flat_trajectory() -> None:
    assert not _maybe_escalate([0.4, 0.5, 0.65], 0, 0.01)        # climbing: stay
    assert _maybe_escalate([0.4, 0.4, 0.4], 0, 0.01)             # flat: escalate
    assert not _maybe_escalate([0.4, 0.4, 0.4], 2, 0.01)         # already at the top rung
    assert not _maybe_escalate([0.4, 0.4], 0, 0.01)              # too early to judge
