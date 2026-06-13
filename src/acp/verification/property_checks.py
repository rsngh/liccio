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


_PBT_GROUNDED_PROMPT = _PBT_PROMPT.replace(
    "EXISTING PUBLIC TEST:\n{public}\n",
    "EXISTING PUBLIC TEST:\n{public}\n\nOBSERVED BUGGY BEHAVIOUR (what the code ABOVE actually does "
    "now — write properties this behaviour VIOLATES but a spec-correct implementation satisfies):\n{trace}\n")


def generate_properties(spec: SpecLike, *, client, model: str = "claude-haiku-4-5",
                        n_prop: int = 6, focus: str = "", trace: str = "") -> tuple[list[str], float]:
    """LLM proposes metamorphic/invariant Hypothesis properties (import-pinned + spec-entailed via the
    shared `_generate`). If `trace` (observed buggy behaviour) is given, generation is execution-grounded
    (AutoVerus-style: condition on what the buggy code actually does). Returns (sources, cost_usd)."""
    if trace:
        return _generate(spec, client=client, model=model, n=n_prop, template=_PBT_GROUNDED_PROMPT,
                         focus=focus or "", trace=trace)
    return _generate(spec, client=client, model=model, n=n_prop, template=_PBT_PROMPT, focus=focus or "")


def behavior_trace(buggy_src: str, focus_names: list[str], public_test: str, *, module_path: str,
                   extra_files: dict[str, str], root: Path) -> str:
    """Reference-free grounding: run the buggy module on the call inputs the PUBLIC test already uses
    against the focus functions, and record each call's actual return/exception. No input synthesis,
    no gold/hidden — just 'here is what the buggy code does today'."""
    import os
    import subprocess
    try:
        ttree = ast.parse(public_test)
    except SyntaxError:
        return ""
    calls: list[str] = []
    for node in ast.walk(ttree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if name in focus_names:
                seg = ast.get_source_segment(public_test, node)
                if seg and seg not in calls:
                    calls.append(seg)
    if not calls:
        return ""
    mod = module_path[:-3].replace("/", ".")
    ws = _build_ws_local(root, module_path, buggy_src, extra_files)
    probe = "import json\nimport " + mod + " as _m\n_o=[]\n"
    for c in calls[:8]:
        expr = c if not c.lstrip().startswith(focus_names[0]) else c   # call as written in the test
        probe += (f"try:\n    _o.append({expr!r} + ' -> ' + repr(eval({expr!r}, "
                  f"{{'__builtins__': __builtins__, **vars(_m)}})))\n"
                  f"except Exception as _e:\n    _o.append({expr!r} + ' -> raises ' + type(_e).__name__)\n")
    probe += "print(chr(10).join(_o))\n"
    (ws / "_trace.py").write_text(probe)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    try:
        r = subprocess.run(["python", "_trace.py"], cwd=ws, capture_output=True, text=True,
                           timeout=30, check=False, env=env)
        return r.stdout.strip()[:1500]
    except subprocess.TimeoutExpired:
        return ""


def _build_ws_local(root: Path, module_path: str, src: str, extra_files: dict[str, str]) -> Path:
    import time
    ws = root / f"trace_{time.time_ns()}"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / module_path).parent.mkdir(parents=True, exist_ok=True)
    (ws / module_path).write_text(src)
    for p, c in extra_files.items():
        (ws / p).parent.mkdir(parents=True, exist_ok=True)
        (ws / p).write_text(c)
    (ws / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    return ws


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


_PROP_ENTAIL_PROMPT = (
    "You are auditing PROPERTY-BASED (Hypothesis) tests for SPEC ENTAILMENT. Each test below asserts an "
    "INVARIANT or METAMORPHIC RELATION over a search space of inputs. A property is only trustworthy if "
    "EVERY spec-correct implementation MUST satisfy it. Flag a property as OVER-SPECIFIED if a correct "
    "implementation of the issue's spec could legitimately VIOLATE it — e.g. it assumes an invariant the "
    "spec never guarantees (a relation that holds for one valid design but not all), constrains output "
    "beyond what the spec states, or asserts behaviour on inputs the spec leaves unspecified. Judge the "
    "ASSERTED RELATION against the spec, not the style.\n\n"
    "Return ONLY a JSON array of the NUMBERS of OVER-SPECIFIED properties (empty array if all are sound).\n\n"
    "ISSUE:\n{issue}\n\nPUBLIC TEST (authoritative):\n{public}\n\nPROPERTIES:\n{tests}\n"
)


def vet_properties(spec: SpecLike, disc_props: list[tuple[str, str]], *, client,
                   model: str = "claude-haiku-4-5") -> tuple[list[tuple[str, str]], int, float]:
    """Drop over-specified PBT discriminators (P12 W1 tightening). A property admitted only because it
    FALSIFIES on buggy can still be WRONG (assert an invariant the spec doesn't guarantee) — and being
    discriminating-by-falsification it then also rejects the gold fix (the strutils harm). This asks a
    property-specific question the generic value-guess filter misses: 'could a CORRECT implementation
    violate this invariant?'. Never drops the whole set (consistency with _entailment_filter). Fail-open.
    Returns (kept, n_dropped, cost_usd)."""
    if client is None or not disc_props:
        return disc_props, 0, 0.0
    import json as _json
    import re as _re
    numbered = "\n\n".join(f"### {j}\n{src}" for j, (_k, src) in enumerate(disc_props))
    prompt = _PROP_ENTAIL_PROMPT.format(issue=getattr(spec, "issue_text", str(spec)),
                                        public=getattr(spec, "public_test", ""), tests=numbered)
    try:
        msg = client.messages.create(model=model, max_tokens=300,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = _re.search(r"\[[\d,\s]*\]", text)
        flagged = {j for j in (set(_json.loads(m.group(0))) if m else set())
                   if isinstance(j, int) and 0 <= j < len(disc_props)}
        usage = getattr(msg, "usage", None)
        cost = round((getattr(usage, "input_tokens", 0) or 0) * 1.0 / 1e6
                     + (getattr(usage, "output_tokens", 0) or 0) * 5.0 / 1e6, 6)
        if flagged and len(flagged) < len(disc_props):     # never drop the whole discriminating set
            kept = [p for j, p in enumerate(disc_props) if j not in flagged]
            return kept, len(disc_props) - len(kept), cost
        return disc_props, 0, cost
    except Exception:  # noqa: BLE001
        return disc_props, 0, 0.0


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
