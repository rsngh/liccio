"""P4: episode graph + procedural recipe (lever-sequence) memory."""

from __future__ import annotations

from acp.memory.episode_graph import (
    build_episode_graph,
    recommend_recipe,
)
from acp.memory.experience_bank import ExperienceEpisode


def _ep(sig: str, *, family="acme/web", task="bugfix", solved=True, recipe=(), reward=1.0,
        symbols=(), tenant="t", decay=1.0) -> ExperienceEpisode:
    return ExperienceEpisode(
        repo_family=family, task_type=task, failure_signature=sig, context_strategy="repo_map",
        agent="x", changed_symbols=tuple(symbols),
        verifier_outcome="solved" if solved else "failed", reward=reward, recipe=tuple(recipe),
        privacy_scope=tenant, decay_score=decay)


def test_graph_links_shared_signature_and_symbols() -> None:
    eps = [
        _ep("AssertionError:median", symbols=("stats.median",)),
        _ep("AssertionError:median", symbols=("stats.median", "stats.mean")),
        _ep("KeyError:config", symbols=("conf.load",)),
    ]
    g = build_episode_graph(eps)
    # 0 and 1 share signature (0.5) + family (0.1) + task (0.1) + symbol overlap -> strong edge
    nb = g.neighbors(0)
    assert nb[0][0] == 1 and nb[0][1] > 0.6
    # 2 has a different signature/symbols; only family+task connect it (weak)
    assert g.adjacency[0][2] < g.adjacency[0][1]


def test_recommend_recipe_direct_picks_best_reward() -> None:
    eps = [
        _ep("E:median", recipe=("haiku", "opus"), reward=0.5),
        _ep("E:median", recipe=("context_first", "haiku"), reward=1.0),   # best
    ]
    rec = recommend_recipe(eps, failure_signature="E:median")
    assert rec.source == "direct"
    assert rec.recipe == ("context_first", "haiku")


def test_recommend_recipe_transfers_from_related_signature() -> None:
    # No solved recipe for the query signature, but a RELATED one (same family+symbols) has one.
    eps = [
        _ep("E:new_symptom", solved=False, recipe=(), symbols=("svc.handler",)),
        _ep("E:old_symptom", solved=True, recipe=("repo_map", "opus"), symbols=("svc.handler",),
            reward=1.0),
    ]
    rec = recommend_recipe(eps, failure_signature="E:new_symptom")
    assert rec.source == "transferred"
    assert rec.from_signature == "E:old_symptom"
    assert rec.recipe == ("repo_map", "opus")


def test_recommend_recipe_none_when_no_procedure() -> None:
    eps = [_ep("E:x", solved=False, recipe=())]
    rec = recommend_recipe(eps, failure_signature="E:x")
    assert rec.source == "none" and rec.recipe == ()


def test_tenant_isolation_blocks_cross_tenant_transfer() -> None:
    eps = [
        _ep("E:y", solved=False, recipe=(), symbols=("a.b",), tenant="t1"),
        _ep("E:y", solved=True, recipe=("haiku",), symbols=("a.b",), tenant="t2"),
    ]
    rec = recommend_recipe(eps, failure_signature="E:y", tenant="t1")
    assert rec.source == "none"     # the only recipe belongs to another tenant
