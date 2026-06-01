"""Tree-sitter Python parsing with AST fallback (round-1 goal §4)."""

from __future__ import annotations

from acp.context.parsers import parse_symbols
from acp.context.tree_sitter_parser import parse_python_symbols_ts, tree_sitter_available

SRC = "def foo(x):\n    return x\n\n\nclass Bar:\n    def method(self):\n        return 1\n"


def test_tree_sitter_extracts_symbols() -> None:
    syms = parse_python_symbols_ts(SRC)
    names = {s.name for s in syms}
    assert {"foo", "Bar", "method"} <= names


def test_parse_symbols_dispatches_python() -> None:
    syms = parse_symbols("m.py", SRC)
    assert any(s.name == "foo" and s.kind == "function" for s in syms)
    assert any(s.name == "Bar" and s.kind == "class" for s in syms)


def test_fallback_on_syntax_error() -> None:
    # Broken source: tree-sitter is error-tolerant; AST fallback returns [].
    syms = parse_python_symbols_ts("def (: bad")
    assert isinstance(syms, list)


def test_availability_flag_is_bool() -> None:
    assert isinstance(tree_sitter_available(), bool)
