"""Counterfactual what-if analysis (Alpha 9)."""

from __future__ import annotations

from acp.routing.counterfactual import total_regret, what_if
from acp.routing.ope import OPESample

CANDS = ["good", "bad"]


def _log(n: int = 40):
    out = []
    for i in range(n):
        a = "good" if i % 2 == 0 else "bad"
        out.append(OPESample("ctx", a, 0.5, 1.0 if a == "good" else 0.0, CANDS))
    return out


def test_what_if_identifies_better_alternative() -> None:
    res = what_if(_log(), "ctx", logged_action="bad", candidate_keys=CANDS)
    assert res.best_action == "good"
    assert res.best_predicted_reward > res.logged_predicted_reward
    assert res.regret > 0.0
    assert res.outcomes[0].action_key == "good"  # sorted best-first


def test_what_if_no_regret_when_logged_is_best() -> None:
    res = what_if(_log(), "ctx", logged_action="good", candidate_keys=CANDS)
    assert res.best_action == "good"
    assert res.regret == 0.0


def test_total_regret_aggregates_over_log() -> None:
    tr = total_regret(_log())
    assert tr["n"] == 40
    # Half the logged actions were the bad arm -> positive mean regret.
    assert tr["mean_regret"] > 0.0
    assert tr["max_regret"] >= tr["mean_regret"]
