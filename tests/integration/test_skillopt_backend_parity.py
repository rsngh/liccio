"""ACP internal SkillOpt backend parity with the real skillopt gate (Alpha 21 WS5)."""

from __future__ import annotations

import pytest

from acp.training.skillopt_backend import (
    ACPInternalSkillOptBackend,
    MicrosoftSkillOptBackend,
)

_CASES = [
    # (cand_score, current_score, best_score) -> expected action
    (1.0, 0.5, 0.5),   # new best
    (0.6, 0.5, 0.8),   # >= current but < best -> accept (not new best)
    (0.3, 0.5, 0.8),   # worse than current -> reject
]


@pytest.mark.parametrize("cand,cur,best", _CASES)
def test_internal_matches_microsoft_gate(cand, cur, best) -> None:
    ms = MicrosoftSkillOptBackend()
    if not ms.available():
        pytest.skip("skillopt not installed")
    internal = ACPInternalSkillOptBackend()
    kw = {"candidate_skill": "cand", "cand_score": cand, "current_skill": "cur",
          "current_score": cur, "best_skill": "best", "best_score": best,
          "best_step": 0, "global_step": 1}
    assert internal.gate(**kw).action == ms.gate(**kw).action


def test_internal_gate_semantics() -> None:
    b = ACPInternalSkillOptBackend()
    assert b.gate(candidate_skill="c", cand_score=1.0, current_skill="u",
                  current_score=0.5, best_skill="x", best_score=0.5, best_step=0,
                  global_step=1).action == "accept_new_best"
    assert b.gate(candidate_skill="c", cand_score=0.3, current_skill="u",
                  current_score=0.5, best_skill="x", best_score=0.8, best_step=0,
                  global_step=1).action == "reject"
