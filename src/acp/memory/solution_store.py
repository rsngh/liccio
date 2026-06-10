# ruff: noqa: E501
"""Procedural / solution memory — cache and REPLAY verified fixes (research: Mem^2, ReMe, ACE).

The ExperienceBank remembers *which rung* solved a (repo_family, failure_signature); it does not keep
the fix itself. But the realistic deployment is repeated work on one codebase — the same test fails
again (CI retry, reopened issue, a regression of a known bug). This store keeps the VERIFIED fixed
function(s) keyed by (repo_family, failure_signature) and replays them by AST-splice into the current
buggy module, so a recurrence is solved with ZERO agent calls — just splice + verify.

Trust-gated: only solutions that passed verification are stored (never a guessed patch). Tenant
isolated and decaying like the ExperienceBank. Dependency-free and deterministic.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SolutionRecord:
    repo_family: str
    failure_signature: str
    module_path: str
    functions: tuple[tuple[str, str], ...]   # (function_name, fixed_source) pairs
    tenant: str = "tenant_a"
    verified: bool = True                     # only verified fixes are admitted
    created_at: float = 0.0


def _func_spans(src: str) -> dict[str, tuple[int, int]]:
    """name -> (start_line, end_line) for top-level + method defs, 1-based (for splice)."""
    out: dict[str, tuple[int, int]] = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
            out[node.name] = (start, node.end_lineno or node.lineno)
    return out


def extract_functions(fixed_module_src: str, names: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Pull the source of the named functions out of a fixed module (to store)."""
    spans = _func_spans(fixed_module_src)
    lines = fixed_module_src.splitlines()
    out = []
    for n in names:
        if n in spans:
            s, e = spans[n]
            out.append((n, "\n".join(lines[s - 1:e])))
    return tuple(out)


def splice_functions(buggy_module_src: str, functions: tuple[tuple[str, str], ...]) -> str | None:
    """Replace the named functions in the buggy module with the cached fixed sources.

    Returns the candidate module, or None if a target function is absent (the module drifted too far
    for a safe replay — caller should fall back to the live ladder)."""
    spans = _func_spans(buggy_module_src)
    lines = buggy_module_src.splitlines()
    # splice from the bottom up so earlier line numbers stay valid
    for name, fixed_src in sorted(functions, key=lambda kv: spans.get(kv[0], (0,))[0], reverse=True):
        if name not in spans:
            return None
        s, e = spans[name]
        indent = len(lines[s - 1]) - len(lines[s - 1].lstrip())
        block = fixed_src.splitlines()
        nonblank = [ln for ln in block if ln.strip()]
        common = min((len(ln) - len(ln.lstrip()) for ln in nonblank), default=0)
        reindented = [((" " * indent) + ln[common:]) if ln.strip() else "" for ln in block]
        lines[s - 1:e] = reindented
    return "\n".join(lines) + "\n"


@dataclass
class SolutionStore:
    """Tenant-isolated cache of verified fixes, keyed by (repo_family, failure_signature)."""

    records: list[SolutionRecord] = field(default_factory=list)

    def record(self, *, repo_family: str, failure_signature: str, module_path: str,
               fixed_module_src: str, function_names: tuple[str, ...], tenant: str = "tenant_a",
               verified: bool, now: float = 0.0) -> bool:
        """Admit a fix ONLY if it verified and we can extract the named functions from it."""
        if not verified:
            return False
        funcs = extract_functions(fixed_module_src, function_names)
        if not funcs:
            return False
        self.records.append(SolutionRecord(repo_family=repo_family, failure_signature=failure_signature,
                                           module_path=module_path, functions=funcs, tenant=tenant,
                                           verified=True, created_at=now))
        return True

    def recall(self, *, tenant: str, repo_family: str, failure_signature: str) -> SolutionRecord | None:
        """Most-recent verified fix for this exact (repo_family, failure_signature), tenant-scoped."""
        hits = [r for r in self.records if r.tenant == tenant and r.repo_family == repo_family
                and r.failure_signature == failure_signature and r.verified]
        return max(hits, key=lambda r: r.created_at) if hits else None

    def replay(self, *, tenant: str, repo_family: str, failure_signature: str,
               buggy_module_src: str) -> str | None:
        """Candidate module from splicing the cached fix into the buggy module (None = no usable hit)."""
        rec = self.recall(tenant=tenant, repo_family=repo_family, failure_signature=failure_signature)
        if rec is None:
            return None
        return splice_functions(buggy_module_src, rec.functions)


def signature_of(test_failure_output: str, changed_symbol: str = "") -> str:
    """Stable failure signature: 'ExceptionType:symbol' from the test output (recurrence key)."""
    import re
    m = re.search(r"\b([A-Z]\w*(?:Error|Exception|Warning))\b", test_failure_output)
    exc = m.group(1) if m else "Failure"
    return f"{exc}:{changed_symbol}" if changed_symbol else exc
