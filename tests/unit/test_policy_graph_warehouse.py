"""Policy-graph warehouse + explorer (Alpha 41)."""

from __future__ import annotations

from acp.routing.policy_graph import PolicyGraph, fold
from acp.routing.policy_graph_warehouse import (
    RepoFamilySignature,
    deserialize_graph,
    explore,
    serialize_graph,
    warm_start_across_repos,
)


def _graph(action="best_of_k", reward=1.0, n=4):
    g = PolicyGraph()
    sig = fold(task_regime="bugfix", single_shot_reliability=0.6)
    for _ in range(n):
        g.update(sig, action, reward)
    return g, sig


def test_serialize_roundtrip_preserves_values() -> None:
    g, sig = _graph()
    snap = serialize_graph(g)
    g2 = deserialize_graph(snap)
    assert g2.value(sig, "best_of_k") == g.value(sig, "best_of_k") == (1.0, 4)


def test_repo_family_signature_extends_key() -> None:
    s = RepoFamilySignature(base_key="bugfix|low|clear", repo_family="frontend",
                            budget_state="low")
    assert "repo=frontend" in s.key() and "budget=low" in s.key()


def test_explore_ranks_best_action_per_signature() -> None:
    g = PolicyGraph()
    sig = fold(task_regime="bugfix", single_shot_reliability=0.6)
    for _ in range(3):
        g.update(sig, "best_of_k", 1.0)
        g.update(sig, "consult_advisor", 0.2)
    out = explore(g)
    assert out["n_signatures"] == 1
    assert out["signatures"][0]["best_action"] == "best_of_k"


def test_warm_start_across_repos_merges() -> None:
    g1, sig = _graph(n=4)
    g2, _ = _graph(n=4)
    merged = warm_start_across_repos([g1, g2], weight=0.5)
    mean, n = merged.value(sig, "best_of_k")
    assert mean > 0 and n >= 1
