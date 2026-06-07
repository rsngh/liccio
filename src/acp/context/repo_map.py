"""Graph-ranked repository map (Aider-style repo map).

Research basis (`pdfs/memory and context/aider-graph-map.pdf`): a coding agent is helped most
by a *concise map of the whole repo* — the key symbols (classes/functions/methods) and their
signatures from everywhere — rather than a handful of vector-retrieved chunks. Aider builds a
graph where files reference symbols defined in other files, ranks symbols by a PageRank-style
centrality (the most-referenced definitions are the most important to understand), and emits
only the highest-ranked signatures that fit a token budget.

This module implements that idea with no heavy dependencies (pure-Python power-iteration
PageRank, tree-sitter/ast symbol extraction via :func:`parse_symbols`). It is deterministic:
the same repo content yields the same map. It complements the chunk retriever — the repo map
gives breadth (signatures from everywhere), retrieval gives depth (full bodies of the few most
relevant chunks).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from acp.context.parsers import parse_symbols

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# identifiers that are too generic to carry signal as cross-file references
_STOP = frozenset({
    "self", "cls", "def", "class", "return", "import", "from", "if", "else", "elif", "for",
    "while", "try", "except", "finally", "with", "as", "in", "is", "and", "or", "not", "None",
    "True", "False", "int", "str", "float", "bool", "list", "dict", "set", "tuple", "len",
    "range", "print", "super", "pass", "raise", "yield", "lambda", "global", "nonlocal",
})


@dataclass
class RankedSymbol:
    path: str
    name: str
    kind: str
    signature: str          # the definition's first line(s), trimmed
    rank: float
    references: int


@dataclass
class RepoMap:
    """A budget-bounded, graph-ranked map of a repo's most important symbols."""

    text: str
    symbols: list[RankedSymbol] = field(default_factory=list)
    token_estimate: int = 0
    files_mapped: int = 0


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _signature(segment: str, kind: str) -> str:
    """First meaningful line(s) of a definition — the signature, not the body."""
    lines = [ln.rstrip() for ln in segment.splitlines() if ln.strip()]
    if not lines:
        return ""
    sig = lines[0]
    # carry continuation lines of a multi-line signature (until the closing ':')
    i = 1
    while not sig.rstrip().endswith(":") and i < len(lines) and i < 6:
        sig += " " + lines[i].strip()
        i += 1
    return sig.strip()


def _pagerank(nodes: list[str], edges: dict[str, dict[str, float]],
              *, damping: float = 0.85, iterations: int = 40) -> dict[str, float]:
    """Weighted PageRank via power iteration (pure Python, deterministic)."""
    n = len(nodes)
    if n == 0:
        return {}
    rank = dict.fromkeys(nodes, 1.0 / n)
    out_w = {u: sum(w.values()) for u, w in edges.items()}
    for _ in range(iterations):
        nxt = dict.fromkeys(nodes, (1.0 - damping) / n)
        dangling = damping * sum(rank[u] for u in nodes if out_w.get(u, 0.0) == 0.0) / n
        for u in nodes:
            ow = out_w.get(u, 0.0)
            if ow == 0.0:
                continue
            ru = damping * rank[u]
            for v, w in edges[u].items():
                nxt[v] += ru * (w / ow)
        for v in nodes:
            nxt[v] += dangling
        rank = nxt
    return rank


def build_repo_map(files: dict[str, str], *, token_budget: int = 1024,
                   max_symbols: int = 400) -> RepoMap:
    """Build a graph-ranked repo map from ``{path: source}``.

    Files reference symbols defined (possibly) in other files; a PageRank over that file graph
    scores how central each file is, and each symbol inherits its definer's centrality scaled by
    how widely it is referenced. The top symbols whose signatures fit ``token_budget`` are
    emitted, grouped by file in path order.
    """
    # 1. Extract definitions: name -> [(path, kind, signature)] and file token sets.
    defs: dict[str, list[tuple[str, str, str]]] = {}
    file_tokens: dict[str, set[str]] = {}
    file_defines: dict[str, set[str]] = {}
    for path in sorted(files):
        src = files[path]
        file_tokens[path] = {t for t in _IDENT.findall(src) if t not in _STOP}
        names: set[str] = set()
        lines = src.splitlines()
        for psym in parse_symbols(path, src):
            seg = "\n".join(lines[psym.start_line - 1 : psym.end_line]) or psym.name
            defs.setdefault(psym.name, []).append(
                (path, psym.kind, _signature(seg, psym.kind)))
            names.add(psym.name)
        file_defines[path] = names

    if not defs:
        return RepoMap(text="", symbols=[], token_estimate=0, files_mapped=0)

    # 2. Build the file reference graph + per-symbol reference counts.
    nodes = sorted(files)
    edges: dict[str, dict[str, float]] = {u: {} for u in nodes}
    references: dict[str, int] = dict.fromkeys(defs, 0)
    for path in nodes:
        for name in file_tokens[path]:
            definers = defs.get(name)
            if not definers:
                continue
            for def_path, _kind, _sig in definers:
                if def_path == path and name in file_defines[path] and len(definers) == 1:
                    continue  # a file referencing only its own private symbol: no cross signal
                references[name] += 1
                if def_path != path:
                    edges[path][def_path] = edges[path].get(def_path, 0.0) + 1.0

    file_rank = _pagerank(nodes, edges)

    # 3. Score each symbol: definer centrality x (1 + log-ish reference weight). Deterministic.
    ranked: list[RankedSymbol] = []
    for name, locs in defs.items():
        refs = references.get(name, 0)
        for path, kind, sig in locs:
            score = file_rank.get(path, 0.0) * (1.0 + refs)
            ranked.append(RankedSymbol(path=path, name=name, kind=kind, signature=sig,
                                       rank=round(score, 8), references=refs))
    ranked.sort(key=lambda s: (-s.rank, s.path, s.name))
    ranked = ranked[:max_symbols]

    # 4. Emit signatures grouped by file (path order), highest-ranked symbols first, to budget.
    chosen: list[RankedSymbol] = []
    used = 0
    seen_files: set[str] = set()
    for sym in ranked:
        # account for the per-file header line ("path:") the first time a file appears
        header = _est_tokens(sym.path + ":") + 1 if sym.path not in seen_files else 0
        cost = _est_tokens(sym.signature) + 1 + header
        if used + cost > token_budget and chosen:
            break
        chosen.append(sym)
        used += cost
        seen_files.add(sym.path)

    by_file: dict[str, list[RankedSymbol]] = {}
    for sym in chosen:
        by_file.setdefault(sym.path, []).append(sym)
    lines_out: list[str] = []
    for path in sorted(by_file):
        lines_out.append(f"{path}:")
        for sym in sorted(by_file[path], key=lambda s: (-s.rank, s.name)):
            lines_out.append(f"  {sym.signature}")
    text = "\n".join(lines_out)
    return RepoMap(text=text, symbols=chosen, token_estimate=_est_tokens(text),
                   files_mapped=len(by_file))
