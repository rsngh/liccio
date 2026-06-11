# ruff: noqa: E501
"""Mutation-based check validation (MuTAP, 2308.16557) — CPU-only, no LLM calls.

A generated check can be syntactically valid yet *insensitive*: its verdict never changes no matter
what the focus region does. Phase 0 showed such checks dilute the battery (and a check the gold fix
fails is actively harmful). MuTAP's remedy: mutate the code under test and measure which checks react.

Adaptation to our buggy-baseline setting: the classic "kill" (test passes on original, fails on
mutant) only fits guard checks. We instead weight every check by *sensitivity* — the fraction of
focus-region mutants on which its verdict FLIPS vs the buggy baseline:
  * guard check (passes on buggy) flipping to FAIL on a mutant  = classic kill (it guards the region);
  * discriminating check (fails on buggy) flipping to PASS      = the mutation moved behaviour toward
    what the check expects — strong evidence the check is keyed to the actual bug region (off-by-one /
    comparison-flip mutants sometimes ARE the fix).
Checks whose verdicts never move across the mutant set are insensitive to the region and get the
floor weight. If no mutant flips anything (or mutation fails), weights degrade to uniform 1.0.

Cost control: one pytest invocation per mutant over ALL check files at once (parse per-file results),
mutants capped, focus-region-only mutation sites.
"""

from __future__ import annotations

import ast
import copy
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

_EPS = 0.1            # weight floor for insensitive checks (never zero: they may still be right)
_MUTANT_TIMEOUT = 25  # one pytest run over all checks for one mutant (a hung mutant must not stall the build)


def _in_spans(lineno: int | None, spans: list[tuple[int, int]] | None) -> bool:
    if spans is None:
        return True
    return lineno is not None and any(s <= lineno <= e for s, e in spans)


def _sites(tree: ast.Module, spans: list[tuple[int, int]] | None) -> list[tuple[int, str]]:
    """Enumerate (site_index, kind) mutation sites in deterministic walk order, span-filtered."""
    out: list[tuple[int, str]] = []
    for i, node in enumerate(ast.walk(tree)):
        if not _in_spans(getattr(node, "lineno", None), spans):
            continue
        if isinstance(node, ast.Compare) and node.ops:
            out.append((i, "cmp"))
        elif isinstance(node, ast.BoolOp):
            out.append((i, "boolop"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub):
            out.append((i, "arith"))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, int)
              and not isinstance(node.value, bool)):
            out.append((i, "const"))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            out.append((i, "not"))
    return out


_CMP_FLIP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
             ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}


def _mutate_at(tree: ast.Module, target: int, kind: str) -> bool:
    """Apply one mutation in-place at walk-index `target`. Returns True if applied."""
    for i, node in enumerate(ast.walk(tree)):
        if i != target:
            continue
        if kind == "cmp":
            flip = _CMP_FLIP.get(type(node.ops[0]))
            if flip is None:
                return False
            node.ops[0] = flip()
        elif kind == "boolop":
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        elif kind == "arith":
            node.op = ast.Sub() if isinstance(node.op, ast.Add) else ast.Add()
        elif kind == "const":
            node.value = node.value + 1
        elif kind == "not":
            return False  # handled by caller (needs parent replacement); skipped in v1
        return True
    return False


def gen_mutants(module_src: str, spans: list[tuple[int, int]] | None = None, *,
                cap: int = 24) -> list[str]:
    """One-mutation-per-mutant variants of `module_src`, sites restricted to `spans` (1-based line
    ranges; None = whole module). Mutants are `ast.unparse`d (formatting loss is fine — they exist
    only to be executed). Capped by interleaving across the site list so coverage spreads."""
    try:
        base = ast.parse(module_src)
    except SyntaxError:
        return []
    sites = [s for s in _sites(base, spans) if s[1] != "not"]
    if not sites:
        return []
    # spread the cap across the region rather than truncating at the top
    step = max(1, len(sites) // cap)
    picked = sites[::step][:cap]
    out: list[str] = []
    for target, kind in picked:
        tree = copy.deepcopy(base)
        if not _mutate_at(tree, target, kind):
            continue
        try:
            src = ast.unparse(ast.fix_missing_locations(tree))
        except Exception:  # noqa: BLE001 - unparse edge case: skip the mutant
            continue
        if src != module_src:
            out.append(src)
    return out


def _run_all_checks_once(module_src: str, checks: list[tuple[str, str]], *, module_path: str,
                         extra_files: dict[str, str], root: Path) -> list[bool] | None:
    """ONE pytest invocation over every check file; per-file verdicts parsed from the summary.
    Returns None on timeout/crash (caller treats as 'no information', not as flips)."""
    ws = root / f"mut_{time.time_ns()}"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / module_path).parent.mkdir(parents=True, exist_ok=True)
    (ws / module_path).write_text(module_src)
    for p, c in extra_files.items():
        (ws / p).parent.mkdir(parents=True, exist_ok=True)
        (ws / p).write_text(c)
    (ws / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    names = []
    for i, (_kind, src) in enumerate(checks):
        name = f"test_battery_{i}.py"
        (ws / name).write_text(src)
        names.append(name)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = ["python", "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider", "-o", "addopts=",
           "--continue-on-collection-errors", *names]
    try:
        p = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=_MUTANT_TIMEOUT,
                           check=False, env=env)
        text = p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired:
        shutil.rmtree(ws, ignore_errors=True)
        return None
    shutil.rmtree(ws, ignore_errors=True)
    bad = set(re.findall(r"(?:FAILED|ERROR)\s+(test_battery_\d+\.py)", text))
    return [f"test_battery_{i}.py" not in bad for i in range(len(checks))]


def sensitivity_weights(baseline_src: str, checks: list[tuple[str, str]],
                        baseline_pass: list[bool], *, module_path: str,
                        extra_files: dict[str, str], root: Path,
                        spans: list[tuple[int, int]] | None = None,
                        cap: int = 16, time_budget_s: float = 150.0,
                        slow_check_s: float = 6.0, skip_check_s: float = 15.0) -> tuple[list[float], dict]:
    """Per-check weights in [_EPS, 1.0] = normalized count of focus-region mutants that flip the
    check's verdict vs the buggy baseline. Uniform 1.0 when mutation yields no information.

    Robustness (the ioutils stall fix): a timed probe run sizes the budget — slow modules get fewer
    mutants and very slow ones skip mutation entirely; an overall wall-clock budget bounds the loop so
    a hung/near-infinite mutant can never stall the battery build."""
    n = len(checks)
    info = {"n_mutants": 0, "n_runs_ok": 0, "skipped": False, "probe_s": 0.0}
    if not n:
        return [], info
    # probe: how slow is ONE run over all checks on the (clean) baseline?
    t0 = time.monotonic()
    probe = _run_all_checks_once(baseline_src, checks, module_path=module_path,
                                 extra_files=extra_files, root=root)
    dt = time.monotonic() - t0
    info["probe_s"] = round(dt, 2)
    if probe is None or dt > skip_check_s:        # too slow / crashing -> don't pay for mutation
        info["skipped"] = True
        return [1.0] * n, info
    eff_cap = max(4, cap // 3) if dt > slow_check_s else cap
    mutants = gen_mutants(baseline_src, spans, cap=eff_cap)
    info["n_mutants"] = len(mutants)
    if not mutants:
        return [1.0] * n, info
    flips = [0] * n
    deadline = time.monotonic() + time_budget_s
    for m in mutants:
        if time.monotonic() > deadline:
            info["budget_hit"] = True
            break
        res = _run_all_checks_once(m, checks, module_path=module_path,
                                   extra_files=extra_files, root=root)
        if res is None:
            continue
        info["n_runs_ok"] += 1
        for j in range(n):
            if res[j] != baseline_pass[j]:
                flips[j] += 1
    top = max(flips)
    info["flips"] = flips
    if top == 0 or info["n_runs_ok"] == 0:
        return [1.0] * n, info   # no signal -> don't punish anyone
    return [max(_EPS, f / top) for f in flips], info
