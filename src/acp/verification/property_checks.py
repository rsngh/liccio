# ruff: noqa: E501
"""Property/metamorphic checks via Hypothesis (P8 W1) — the discrimination lever.

P7 measured the wall: LLM-written EXAMPLE tests can't guess the input that triggers a subtle bug, so
~64% of batteries are non-discriminating (buggy and gold both pass). The fix (Anthropic agentic-PBT
2026; metamorphic-testing-for-APR 2410.07516): let the LLM propose a PROPERTY / metamorphic relation
(idempotence, round-trip, commutativity, bounds, monotonicity, no-raise, type-stability) and let
**Hypothesis search the inputs** that break it. ~50x more bug-discrimination than hand-written tests.

The principled admission gate (`admit_discriminating`): a property is counted DISCRIMINATING only if,
run on the BUGGY baseline, Hypothesis finds a falsifying example (verdict "assert") — i.e. we *prove*
it exercises the bug rather than guessing. Properties that hold on buggy are GUARDS; properties that
error (API misuse / unsatisfiable strategy) are dropped. Properties are ordinary pytest files, so they
flow through the existing battery machinery (`_run_checks`, discriminating/guard split, scoring)
unchanged — this module only generates, bounds, and admits them.
"""

from __future__ import annotations

import ast
from pathlib import Path

from acp.verification.repair_battery import (
    SpecLike,
    _collects_cleanly,
    _generate,
    _run_check_kinds,
)

# A bounded Hypothesis profile injected into every generated property (the PBT analog of the
# per-check subprocess timeout in repair_battery._run_checks). deadline=None: wall-clock is bounded by
# the subprocess timeout in _run_check_kinds, so we don't want Hypothesis' own deadline turning a slow
# (but correct) property into a spurious "discriminating" failure.
_HARDEN = (
    "from hypothesis import settings as _acp_settings, HealthCheck as _acp_HC\n"
    "_acp_settings.register_profile('acp_pbt', max_examples=60, deadline=None,\n"
    "    suppress_health_check=[_acp_HC.too_slow, _acp_HC.filter_too_much, _acp_HC.data_too_large])\n"
    "_acp_settings.load_profile('acp_pbt')\n"
)

_PBT_PROMPT = (
    "You are a senior test engineer writing PROPERTY-BASED tests with the Hypothesis library. Write {n} "
    "NEW, self-contained Hypothesis tests that assert INVARIANTS / METAMORPHIC RELATIONS the spec "
    "guarantees — e.g. idempotence f(f(x))==f(x), round-trip decode(encode(x))==x, commutativity, "
    "order-independence, monotonicity, output bounds/ranges, 'does not raise on valid input', or "
    "type-stability. Use `@given(...)` with `hypothesis.strategies` to let Hypothesis SEARCH the input "
    "space (do not hard-code a handful of literal inputs). Each test is a complete file: imports + one "
    "`@given(...) def test_prop(...)`. Constrain strategies to the domain the spec implies.\n\n"
    "{import_rule}\n{entail_rule}\n"
    "Return ONLY a JSON array of strings; each string is a complete test file.\n\n"
    "ISSUE:\n{issue}\n\nBUGGY CODE (the suspected region — write properties its behaviour violates):\n"
    "```python\n{focus}\n```\n\nEXISTING PUBLIC TEST:\n{public}\n"
)


def generate_properties(spec: SpecLike, *, client, model: str = "claude-haiku-4-5",
                        n_prop: int = 6, focus: str = "") -> tuple[list[str], float]:
    """LLM proposes metamorphic/invariant Hypothesis properties (import-pinned + spec-entailed via the
    shared `_generate`). Returns (raw_property_sources, cost_usd)."""
    return _generate(spec, client=client, model=model, n=n_prop, template=_PBT_PROMPT, focus=focus or "")


def harden_property(src: str) -> str:
    """Inject the bounded Hypothesis profile after the property's own imports so `@given` picks it up.
    Falls back to a simple prepend if the file doesn't parse."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return _HARDEN + src
    last_import = 0
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            last_import = node.end_lineno or node.lineno
        else:
            break
    lines = src.splitlines()
    return "\n".join(lines[:last_import] + _HARDEN.splitlines() + lines[last_import:]) + "\n"


def admit_discriminating(props: list[str], *, baseline_src: str, module_path: str,
                         extra_files: dict[str, str], root: Path,
                         tag: str = "pbt") -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Collect-filter + classify hardened properties against the BUGGY baseline.

    'assert' (Hypothesis falsified it on buggy) -> DISCRIMINATING (proven to exercise the bug);
    'pass' (held on buggy)                       -> GUARD (must keep holding);
    'error' (API misuse / unsatisfiable)         -> dropped.
    Returns (discriminating, guard) as (kind="pbt", src) tuples ready to append to a battery."""
    hardened = [harden_property(p) for p in props]
    ok = [h for h in hardened
          if _collects_cleanly(h, module_path=module_path, baseline_src=baseline_src,
                               extra_files=extra_files, root=root)]
    if not ok:
        return [], []
    pairs = [("pbt", h) for h in ok]
    kinds = _run_check_kinds(baseline_src, pairs, module_path=module_path,
                             extra_files=extra_files, root=root, tag=tag)
    discriminating = [p for p, k in zip(pairs, kinds, strict=True) if k == "assert"]
    guard = [p for p, k in zip(pairs, kinds, strict=True) if k == "pass"]
    return discriminating, guard
