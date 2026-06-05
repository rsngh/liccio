"""Context-strategy optimizer: grep vs embeddings vs hybrid (Alpha 24 area 6)."""

from __future__ import annotations

import pytest

from acp.context.strategy_optimizer import (
    ContextObservation,
    amortized_cost,
    choose_strategy,
)


def test_grep_wins_when_it_matches_embeddings_at_lower_cost() -> None:
    obs = [
        ContextObservation("grep", downstream_success=0.9, tokens=2000, latency_s=0.2),
        ContextObservation("embedding", downstream_success=0.9, tokens=4000, latency_s=0.6,
                           index_build_tokens=200000, reuse_count=10),
    ]
    d = choose_strategy(obs)
    assert d.chosen == "grep"  # equal success, lower cost -> grep
    assert "embedding not chosen" in d.reason


def test_embedding_wins_when_its_downstream_success_justifies_cost() -> None:
    obs = [
        ContextObservation("grep", downstream_success=0.5, tokens=2000, latency_s=0.2),
        ContextObservation("embedding", downstream_success=0.95, tokens=4000, latency_s=0.6,
                           index_build_tokens=100000, reuse_count=1000),
    ]
    assert choose_strategy(obs).chosen == "embedding"


def test_reuse_amortizes_index_cost() -> None:
    once = ContextObservation("embedding", 0.9, 1000, 0.5, index_build_tokens=100000,
                              reuse_count=1)
    many = ContextObservation("embedding", 0.9, 1000, 0.5, index_build_tokens=100000,
                              reuse_count=1000)
    assert amortized_cost(many) < amortized_cost(once)


def test_no_evidence_defaults_to_grep() -> None:
    assert choose_strategy([]).chosen == "grep"


def test_unknown_strategy_rejected() -> None:
    with pytest.raises(ValueError):
        ContextObservation("vector_magic", 0.9, 1000, 0.5)
