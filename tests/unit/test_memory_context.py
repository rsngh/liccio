"""P12: embedding-kNN routing memory (ACRouter) — store, retrieval, and non-breaking enrichment."""

from __future__ import annotations

from acp.core.enums import RiskLevel, TaskType
from acp.routing import MemoryContext, RoutingFeatureExtractor, SimulatedBanditPolicy
from acp.routing.actions import candidate_actions
from acp.schemas.task import Task


def _task(title: str, body: str = "") -> Task:
    return Task(repo_id="r1", title=title, body=body,
                task_type=TaskType.BUGFIX, risk_level=RiskLevel.MEDIUM)


def test_query_returns_best_action_from_similar_neighbours() -> None:
    m = MemoryContext(threshold=0.1)
    for _ in range(3):
        m.add("fix null pointer in the json parser", "claude", reward=2.0)
    m.add("fix null pointer in the json parser", "codex", reward=-1.0)
    nbr = m.query("null pointer json parser crash")
    assert not nbr.sparse
    assert nbr.best_action == "claude"                      # higher mean reward among neighbours
    assert nbr.action_reward["claude"] > nbr.action_reward["codex"]
    assert nbr.action_n["claude"] == 3


def test_empty_and_dissimilar_are_sparse() -> None:
    m = MemoryContext(threshold=0.9)
    assert m.query("anything").sparse                       # empty store
    m.add("refactor the database connection pool", "claude", reward=1.0)
    assert m.query("unrelated topic about weather forecasts").sparse  # below threshold


def test_fifo_bound() -> None:
    m = MemoryContext(maxlen=5)
    for i in range(20):
        m.add(f"task number {i}", "claude", reward=1.0)
    assert len(m) == 5


def test_extract_is_unchanged_without_memory() -> None:
    f = RoutingFeatureExtractor().extract(_task("fix bug"))
    assert "neighbor_count" not in f and "neighbor_action_reward" not in f
    assert RoutingFeatureExtractor.context_key(f) == "bugfix|medium"


def test_extract_enriches_with_memory() -> None:
    m = MemoryContext(threshold=0.1)
    for _ in range(2):
        m.add("fix off-by-one in pagination", "claude", reward=3.0)
    f = RoutingFeatureExtractor().extract(_task("fix off-by-one in pagination"), memory=m)
    assert f["neighbor_count"] >= 1
    assert f["neighbor_best_action"] == "claude"
    # context_key is NOT affected by enrichment
    assert RoutingFeatureExtractor.context_key(f) == "bugfix|medium"


def test_bandit_cold_start_prior_from_memory_then_unchanged_without() -> None:
    cands = candidate_actions(available_agents=["claude", "codex"], strategies=["hybrid"])
    keys = [c.key() for c in cands]
    # neighbour evidence strongly favours the FIRST candidate's action
    feats_mem = {"task_type": "bugfix", "risk_level": "medium",
                 "neighbor_action_reward": {keys[0]: 5.0, keys[1]: -5.0}}
    pol = SimulatedBanditPolicy(epsilon=0.0)                 # pure exploit -> prior decides
    dec = pol.choose_action(feats_mem, cands)
    assert dec.action.key() == keys[0]                       # cold arms seeded from neighbours
    # no neighbour key -> cold arms tie at 0.0; behaviour identical to before (no crash, valid pick)
    pol2 = SimulatedBanditPolicy(epsilon=0.0)
    dec2 = pol2.choose_action({"task_type": "bugfix", "risk_level": "medium"}, cands)
    assert dec2.action.key() in keys
