"""Real Tree-sitter symbol extraction for Python (round-1 goal §4).

Uses the installed ``tree-sitter`` + ``tree-sitter-python`` grammar to walk a
concrete syntax tree. Falls back to the stdlib ``ast`` parser when tree-sitter
(or the grammar) is unavailable, so behavior is identical without the optional
dependency.
"""

from __future__ import annotations

from acp.context.parsers import Symbol, parse_python_symbols
from acp.core.optional import try_import

_PARSER = None
_AVAILABLE: bool | None = None


def _get_parser():
    global _PARSER, _AVAILABLE
    if _AVAILABLE is not None:
        return _PARSER
    ts = try_import("tree_sitter")
    tsp = try_import("tree_sitter_python")
    if ts is None or tsp is None:
        _AVAILABLE = False
        return None
    try:
        language = ts.Language(tsp.language())
        parser = ts.Parser(language)
        _PARSER = parser
        _AVAILABLE = True
    except Exception:  # noqa: BLE001 - any grammar/version mismatch -> fallback
        _AVAILABLE = False
        _PARSER = None
    return _PARSER


def tree_sitter_available() -> bool:
    _get_parser()
    return bool(_AVAILABLE)


def parse_python_symbols_ts(source: str) -> list[Symbol]:
    """Extract function/class symbols via Tree-sitter; AST fallback on failure."""
    parser = _get_parser()
    if parser is None:
        return parse_python_symbols(source)
    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return parse_python_symbols(source)

    symbols: list[Symbol] = []

    def visit(node) -> None:
        if node.type in ("function_definition", "class_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = source.encode("utf-8")[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8", "replace"
                )
                kind = "class" if node.type == "class_definition" else "function"
                symbols.append(
                    Symbol(name, kind, node.start_point[0] + 1, node.end_point[0] + 1)
                )
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return symbols or parse_python_symbols(source)
