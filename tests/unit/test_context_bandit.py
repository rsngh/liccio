"""Context-strategy bandit tests (GOALS Alpha 43 P5)."""

from __future__ import annotations

from acp.context.context_bandit import ContextBandit


def test_bandit_learns_best_strategy_per_need() -> None:
    b = ContextBandit(epsilon=0.0, seed=1)        # pure exploit after seeding
    for _ in range(20):
        b.update("cross_file_api", "repo_map", reward=1.0, cost=0.0015)
        b.update("cross_file_api", "none", reward=0.0, cost=0.001)
    assert b.best("cross_file_api") == "repo_map"
    assert b.select("cross_file_api") == "repo_map"


def test_cheaper_strategy_wins_on_reward_tie() -> None:
    b = ContextBandit(epsilon=0.0, seed=1)
    for _ in range(10):
        b.update("none", "none", reward=1.0, cost=0.001)
        b.update("none", "repo_map", reward=1.0, cost=0.005)
    assert b.best("none") == "none"               # equal reward -> cheaper arm


def test_exploration_is_deterministic_with_seed() -> None:
    a = ContextBandit(epsilon=1.0, seed=42)
    c = ContextBandit(epsilon=1.0, seed=42)
    picks_a = [a.select("x") for _ in range(15)]
    picks_c = [c.select("x") for _ in range(15)]
    assert picks_a == picks_c                     # reproducible exploration


def test_policy_and_stats() -> None:
    b = ContextBandit(epsilon=0.0, seed=1)
    b.update("exact_symbol", "grep", reward=1.0, cost=0.0005)
    pol = b.policy()
    assert pol["exact_symbol"] == "grep"
    assert b.stats()["exact_symbol|grep"]["n"] == 1
