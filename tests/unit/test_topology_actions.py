"""Topology action learning (Alpha 11/12, WS8)."""

from __future__ import annotations

from acp.core.enums import AgentKind
from acp.routing.actions import CandidateGenerator
from acp.routing.ope import OPESample, evaluate_policy, fit_reward_model
from acp.schemas.routing import TOPOLOGY_ACTIONS, RoutingAction


def _base() -> RoutingAction:
    return RoutingAction(agent_kind=AgentKind.CLAUDE, agent_name="claude_harness")


def test_topology_actions_defined() -> None:
    assert "skip_reviewer" in TOPOLOGY_ACTIONS
    assert "branch_parallel" in TOPOLOGY_ACTIONS
    assert "abstain" in TOPOLOGY_ACTIONS
    assert len(TOPOLOGY_ACTIONS) == 10


def test_default_action_key_is_backward_compatible() -> None:
    # No topology -> key unchanged (5 parts), so existing logs/arms still match.
    a = _base()
    assert a.key().count("|") == 4
    assert "topo:" not in a.key()


def test_topology_changes_arm_key() -> None:
    a = _base()
    b = a.model_copy(update={"topology": ["skip_reviewer"]})
    assert a.key() != b.key()
    assert "topo:skip_reviewer" in b.key()
    # Topology is order-independent in the key.
    c = a.model_copy(update={"topology": ["run_light_verifier", "skip_planner"]})
    d = a.model_copy(update={"topology": ["skip_planner", "run_light_verifier"]})
    assert c.key() == d.key()


def test_candidate_generator_emits_topology_variants() -> None:
    gen = CandidateGenerator(topologies=[[], ["skip_reviewer"], ["branch_parallel"]])
    cands = gen.generate(_base(), ["claude_harness"])
    keys = {c.key() for c in cands}
    assert len(keys) == 3  # one per topology variant
    assert any("skip_reviewer" in k for k in keys)


def test_topology_arm_learnable_via_ope() -> None:
    # A "skip_reviewer" shape solves a cheap task; the full shape over-verifies.
    full = _base().key()
    skip = _base().model_copy(update={"topology": ["skip_reviewer"]}).key()
    cands = [full, skip]
    log = [OPESample("docs|low", skip if i % 2 == 0 else full, 0.5,
                     1.0 if i % 2 == 0 else 0.4, cands) for i in range(40)]
    q = fit_reward_model(log)

    def greedy(ctx, action, c):
        best = max(q(ctx, a) for a in c)
        return 1.0 if action == max(c, key=lambda a: q(ctx, a)) and q(ctx, action) == best else 0.0

    val = evaluate_policy(log, greedy, seed=1).dr.value
    assert val > 0.5  # the learned shape beats the logged mix
