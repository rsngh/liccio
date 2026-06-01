"""Retrieval + scoring tests (charter §10.3)."""

from __future__ import annotations

from acp.context.chunks import make_chunk
from acp.context.retrieval import HybridRetriever


def _items() -> list:
    return [
        make_chunk(kind="file_chunk", path="src/calculator.py",
                   content="def divide(a, b): return a / b"),
        make_chunk(kind="test_chunk", path="tests/test_calc.py",
                   content="def test_divide(): assert divide(6,2)==3"),
        make_chunk(kind="file_chunk", path="src/unrelated.py",
                   content="def greet(): print('hello world')"),
    ]


def test_relevant_chunks_outrank_unrelated() -> None:
    r = HybridRetriever(_items())
    scored, trace = r.retrieve("divide by zero in calculator", top_k=3)
    ranks = {s.item.path: i for i, s in enumerate(scored)}
    # both calculator source and its test should outrank the unrelated file
    assert ranks["src/calculator.py"] < ranks["src/unrelated.py"]
    assert ranks["tests/test_calc.py"] < ranks["src/unrelated.py"]
    assert trace.considered == 3
    assert trace.selected == 3


def test_keyword_only_zeroes_vector() -> None:
    r = HybridRetriever(_items())
    scored, _ = r.retrieve("divide", strategy="keyword_only", top_k=3)
    for s in scored:
        assert s.components["vector"] == 0.0


def test_test_focused_boosts_tests() -> None:
    r = HybridRetriever(_items())
    scored, _ = r.retrieve("divide", strategy="test_focused", top_k=3)
    test_item = next(s for s in scored if s.item.kind == "test_chunk")
    assert test_item.components["test"] > 0.0


def _mixed_items() -> list:
    return [
        make_chunk(kind="doc_chunk", path="README.md", content="architecture overview module"),
        make_chunk(kind="manifest_chunk", path="pyproject.toml", content="deps module"),
        make_chunk(kind="test_chunk", path="tests/test_m.py", content="def test_m(): module"),
        make_chunk(kind="symbol_chunk", path="m.py", content="def m(): pass", symbol_name="m"),
        make_chunk(kind="file_chunk", path="m.py", content="module body here"),
    ]


def test_architecture_strategy_prefers_docs() -> None:
    r = HybridRetriever(_mixed_items())
    scored, _ = r.retrieve("module", strategy="architecture", top_k=5)
    top_kinds = [s.item.kind for s in scored[:2]]
    assert "doc_chunk" in top_kinds or "manifest_chunk" in top_kinds


def test_bug_reproduction_prefers_tests_symbols() -> None:
    r = HybridRetriever(_mixed_items())
    scored, _ = r.retrieve("module", strategy="bug_reproduction", top_k=5)
    top_kinds = [s.item.kind for s in scored[:2]]
    assert "test_chunk" in top_kinds or "symbol_chunk" in top_kinds


def test_minimal_strategy_caps_items() -> None:
    items = [make_chunk(kind="file_chunk", path=f"f{i}.py", content=f"x{i} module")
             for i in range(30)]
    r = HybridRetriever(items)
    scored, _ = r.retrieve("module", strategy="minimal", top_k=60)
    assert len(scored) <= 8


def test_strategies_yield_different_orderings() -> None:
    items = _mixed_items()
    arch, _ = HybridRetriever(items).retrieve("module", strategy="architecture")
    bug, _ = HybridRetriever(items).retrieve("module", strategy="bug_reproduction")
    assert [s.item.path for s in arch] != [s.item.path for s in bug]


def test_scores_are_deterministic() -> None:
    a, _ = HybridRetriever(_items()).retrieve("divide calculator")
    b, _ = HybridRetriever(_items()).retrieve("divide calculator")
    assert [round(s.score, 6) for s in a] == [round(s.score, 6) for s in b]
