"""Supervised meta-router (Alpha 6, WS4) + OPE comparison vs bandit/random."""

from __future__ import annotations

import pytest

from acp.core.enums import AgentKind
from acp.routing.bandit import SimulatedBanditPolicy
from acp.routing.ope import OPESample, evaluate_policy
from acp.routing.policy import PolicyDecision, RoutingPolicy
from acp.routing.supervised import SupervisedRoutingPolicy, featurize
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction

# Synthetic world: task_type "bugfix", two agents. "claude_harness" solves it
# (reward 1), "fake" does not (reward 0). The logging policy is uniform.
CTX = "bugfix|medium"


def _action(agent: str) -> RoutingAction:
    return RoutingAction(agent_kind=AgentKind.CLAUDE if agent != "fake" else AgentKind.FAKE,
                         agent_name=agent, context_strategy="hybrid_keyword_embedding")


GOOD = _action("claude_harness")
BAD = _action("fake")
CANDS = [GOOD, BAD]
CAND_KEYS = [GOOD.key(), BAD.key()]


def _reward(agent: str) -> float:
    return 1.0 if agent != "fake" else 0.0


def _training_rows(n: int = 60) -> list[dict]:
    rows = []
    for i in range(n):
        agent = "claude_harness" if i % 2 == 0 else "fake"
        rows.append({"context_key": CTX, "action_key": _action(agent).key(),
                     "reward": _reward(agent)})
    return rows


def _uniform_log(n: int = 120) -> list[OPESample]:
    out = []
    for i in range(n):
        agent = "claude_harness" if i % 2 == 0 else "fake"
        out.append(OPESample(CTX, _action(agent).key(), behavior_prob=0.5,
                             reward=_reward(agent), candidates=CAND_KEYS))
    return out


def test_implements_routing_policy_protocol() -> None:
    pol = SupervisedRoutingPolicy()
    assert isinstance(pol, RoutingPolicy)


def test_featurize_generalizes_tokens() -> None:
    f = featurize("bugfix|medium", "harness|claude_harness|-|test_focused|standard")
    assert f["ctx=bugfix"] == 1.0
    assert f["act=claude_harness"] == 1.0
    assert f["act=test_focused"] == 1.0
    assert "act=-" not in f  # placeholder tokens dropped


def test_cold_start_is_uniform() -> None:
    pol = SupervisedRoutingPolicy()
    dist = pol.action_distribution(CTX, CAND_KEYS)
    assert dist[GOOD.key()] == dist[BAD.key()] == 0.5


def test_fitted_policy_prefers_the_good_agent() -> None:
    pytest.importorskip("sklearn")  # learned predictor needs scikit-learn (data/learning extra)
    pol = SupervisedRoutingPolicy()
    pol.fit(_training_rows())
    assert pol.predicted_reward(CTX, GOOD.key()) > pol.predicted_reward(CTX, BAD.key())
    dec = pol.choose_action({"task_type": "bugfix", "risk_level": "medium"}, CANDS)
    assert dec.action.agent_name == "claude_harness"


def test_choose_action_returns_valid_propensity() -> None:
    pol = SupervisedRoutingPolicy(epsilon=0.1)
    pol.fit(_training_rows())
    dec = pol.choose_action({"task_type": "bugfix", "risk_level": "medium"}, CANDS)
    assert 0.0 < dec.action_probability <= 1.0
    assert isinstance(dec, PolicyDecision)


def test_supervised_beats_random_and_ties_bandit_under_ope() -> None:
    """WS4 acceptance: on the logged data, OPE values supervised >= random,
    and supervised is at least as good as the bandit."""
    pytest.importorskip("sklearn")  # learned predictor needs scikit-learn (data/learning extra)
    log = _uniform_log()

    supervised = SupervisedRoutingPolicy()
    supervised.fit(_training_rows())

    def random_target(ctx, action, cands):
        return 1.0 / len(cands)

    sup_val = evaluate_policy(log, supervised.as_target(), seed=1).dr.value
    rnd_val = evaluate_policy(log, random_target, seed=1).dr.value
    assert sup_val > rnd_val

    # Train a bandit on the same outcomes and compare its greedy target.
    bandit = SimulatedBanditPolicy(epsilon=0.0)
    for i in range(120):
        agent = "claude_harness" if i % 2 == 0 else "fake"
        dec = PolicyDecision(policy_version="b", action=_action(agent),
                             action_probability=0.5, context_key=CTX)
        bandit.observe_reward(dec, RewardEvent(task_id="t", reward=_reward(agent),
                                               components={"objective": _reward(agent)}))

    def bandit_target(ctx, action, cands):
        arms = bandit.arms.get(ctx, {})
        if not arms:
            return 1.0 / len(cands)
        best = max(arms.get(k).mean if arms.get(k) else 0.0 for k in cands)
        winners = [k for k in cands if arms.get(k) and arms[k].mean == best]
        return 1.0 / len(winners) if action in winners else 0.0

    ban_val = evaluate_policy(log, bandit_target, seed=1).dr.value
    assert sup_val >= ban_val - 1e-6  # supervised at least ties the bandit
