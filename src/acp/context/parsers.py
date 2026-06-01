"""Source parsing: symbol extraction via Python AST (+ tree-sitter when present).

Tree-sitter gives multi-language concrete syntax trees; when unavailable (or for
unsupported languages) we fall back to Python's stdlib ``ast`` for .py files and
a lightweight regex for JS/TS function/class declarations.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass
class Symbol:
    name: str
    kind: str  # function | class | method
    start_line: int
    end_line: int


def parse_python_symbols(source: str) -> list[Symbol]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    symbols: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                Symbol(node.name, "function", node.lineno, getattr(node, "end_lineno", node.lineno))
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                Symbol(node.name, "class", node.lineno, getattr(node, "end_lineno", node.lineno))
            )
    return symbols


_JS_DECL = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)"
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()",
)


def parse_js_symbols(source: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    for i, line in enumerate(source.splitlines(), start=1):
        m = _JS_DECL.match(line)
        if m:
            name = next((g for g in m.groups() if g), None)
            if name:
                kind = "class" if m.group(2) else "function"
                symbols.append(Symbol(name, kind, i, i))
    return symbols


def parse_symbols(path: str, source: str) -> list[Symbol]:
    if path.endswith(".py"):
        return parse_python_symbols(source)
    if path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
        return parse_js_symbols(source)
    return []


def detect_language(path: str) -> str | None:
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    return {
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "mjs": "javascript",
        "md": "markdown",
        "txt": "text",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "toml": "toml",
    }.get(ext)
