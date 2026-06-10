# ruff: noqa: E501
"""Boosted localized repair (v2) — the convergent recipe from the pdfs/ research corpus.

The measured bottleneck (issue_replay_diagnosis.json) is "right function located, WRONG fix written"
— the v1 pipeline hands the model the correct buggy function and a failing test and still gets a bad
patch 80% of the time. The 58 papers in pdfs/ converge on four cheap mechanisms that attack exactly
this, all implemented here on top of the v1 localize->splice machinery:

  1. RATIONALE CONTEXT (RepFuse 2402.14323; aider repo-map): the prompt carries the module's
     skeleton (imports + class/def signature map) and sibling-module signatures, so the fix is
     grounded in the real API surface instead of just the isolated function body.
  2. ATTEMPT MEMORY (Reflexion 2303.11366): every failed patch is summarized (capped diff) and fed
     back as "these patches FAILED — do not repeat them", preventing the dominant failure of
     re-emitting the same wrong fix at higher temperature.
  3. CRITIC ROUND (MAR 2512.10696, committee-boosting 2605.14163): between rounds, one cheap call
     plays skeptic — given the failed patch and the test output it must diagnose the ROOT CAUSE,
     and the next round's prompt conditions on that diagnosis (proposer/critic separation).
  4. EARLY PRUNE + DEDUPE (VerMCTS 2402.08147): candidates that do not AST-parse, or whose AST hash
     equals an already-failed candidate, are dropped before paying for a test run.

Grading is unchanged and ungamed: the pristine held-out test runs on the produced module.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
from pathlib import Path

from evals.issue_replay.repair_harness import (
    _extract,
    _first_block,
    _func_table,
    _llm,
    _localize,
    _parse_funcs,
    _run,
    _splice,
)
from evals.issue_replay.replay_task import IssueReplayTask

from acp.routing.reflective_repair import failure_summary


def module_skeleton(src: str, *, max_lines: int = 80) -> str:
    """Imports + class/def signature lines (the aider repo-map idea, single-module scale)."""
    out: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    lines = src.splitlines()
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            out.append(lines[node.lineno - 1])
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out.append(f"class {node.name}:")
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    out.append(f"    def {sub.name}({', '.join(a.arg for a in sub.args.args)}): ...")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and isinstance(node, ast.stmt):
            parent_is_module = any(node is n for n in tree.body)
            if parent_is_module:
                out.append(f"def {node.name}({', '.join(a.arg for a in node.args.args)}): ...")
    return "\n".join(out[:max_lines])


def sibling_signatures(extra_files: dict[str, str], *, max_sibs: int = 6, per_sib: int = 12) -> str:
    """Top-level def/class names of sibling modules (package bundles), so cross-module calls resolve."""
    chunks: list[str] = []
    for path, src in list(extra_files.items())[:max_sibs]:
        if not path.endswith(".py") or path.endswith("__init__.py"):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        names = [f"{'class' if isinstance(n, ast.ClassDef) else 'def'} {n.name}" for n in tree.body
                 if isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)][:per_sib]
        if names:
            chunks.append(f"# {path}: " + ", ".join(names))
    return "\n".join(chunks)


def _diff_cap(old: str, new: str, *, cap: int = 30) -> str:
    d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1))[2:]
    return "\n".join(d[:cap])


def _ast_hash(src: str) -> str:
    try:
        return hashlib.sha256(ast.dump(ast.parse(src)).encode()).hexdigest()[:16]
    except SyntaxError:
        return ""


_PROMPT = (
    "You are fixing a bug in a Python module. {instr}\n\n"
    "ISSUE: {issue}\n\n"
    "MODULE API MAP (imports + signatures, for grounding — do not rewrite these):\n{skeleton}\n\n"
    "{siblings}"
    "CODE (the suspected buggy region):\n```python\n{focus}\n```\n\n"
    "TEST FAILURE (fix the real cause):\n{failure}\n\n"
    "{diagnosis}{failed}"
)

_CRITIC = (
    "You are a skeptical code reviewer. A proposed patch FAILED the test. Diagnose the ROOT CAUSE "
    "in <=5 sentences: what does the test actually require, and why does the patch (and the original "
    "code) not satisfy it? Be concrete about expected-vs-got values. Do NOT write code.\n\n"
    "ISSUE: {issue}\n\nBUGGY REGION:\n```python\n{focus}\n```\n\n"
    "FAILED PATCH (unified diff):\n{diff}\n\nTEST OUTPUT:\n{failure}\n"
)


def repair_v2(task: IssueReplayTask, root: Path, *, model_id: str, rate: tuple[float, float],
              k: int = 3, rounds: int = 3) -> tuple[str, float, bool]:
    """Boosted localized repair. Returns (produced_module_src, cost_usd, ran)."""
    work = root / f"r2_{abs(hash(task.repo_name + task.issue_title)) % 100000}"
    work.mkdir(parents=True, exist_ok=True)
    for p, c in task.extra_files.items():
        (work / p).parent.mkdir(parents=True, exist_ok=True)
        (work / p).write_text(c)
    (work / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    (work / "test_repro.py").write_text(task.hidden_test)
    (work / task.module_path).parent.mkdir(parents=True, exist_ok=True)

    def repro(module_src: str) -> tuple[bool, str]:
        (work / task.module_path).write_text(module_src)
        return _run(work, "test_repro.py")

    current = task.buggy
    _, output = repro(current)
    failure = failure_summary(output)
    table = _func_table(current)
    focus_names = _localize(current, task.issue_title, task.hidden_test, output)
    whole = not focus_names
    focus = _extract(current, focus_names, table) if focus_names else current[:14000]
    skeleton = module_skeleton(current) or "(unavailable)"
    sibs = sibling_signatures(task.extra_files)
    sib_block = f"SIBLING MODULES (callable API):\n{sibs}\n\n" if sibs else ""
    instr = ("Return ONLY the full corrected module in a ```python code block."
             if whole else
             "Return ONLY the corrected full definition(s) of the function(s) shown, in a "
             "```python code block — same names, same signatures, nothing else.")

    cost = 0.0
    ran = False
    diagnosis = ""
    failed_patches: list[str] = []
    seen_hashes = {_ast_hash(current)}
    best_cand, best_diff = current, ""
    for rnd in range(rounds):
        diag_block = f"REVIEWER DIAGNOSIS (address this directly):\n{diagnosis}\n\n" if diagnosis else ""
        failed_block = ("PATCHES THAT ALREADY FAILED — do NOT repeat these approaches:\n"
                        + "\n---\n".join(failed_patches[-3:]) + "\n") if failed_patches else ""
        prompt = _PROMPT.format(instr=instr, issue=f"{task.issue_title}\n{task.issue_body}",
                                skeleton=skeleton, siblings=sib_block, focus=focus,
                                failure=failure, diagnosis=diag_block, failed=failed_block)
        temps = [0.0, 0.7, 1.0] if rnd == 0 else [0.4, 0.8, 1.0]
        for i in range(k):
            try:
                text, it, ot = _llm(model_id, prompt, temperature=temps[min(i, len(temps) - 1)])
            except Exception:  # noqa: BLE001 - provider hiccup: skip the sample, keep the round going
                continue
            ran = True
            cost += it * rate[0] + ot * rate[1]
            if whole:
                cand = _first_block(text) or current
            else:
                funcs = _parse_funcs(text)
                cand = _splice(current, table, funcs) if funcs else current
            h = _ast_hash(cand)
            if not h or h in seen_hashes:        # early prune: unparseable or already-tried patch
                continue
            seen_hashes.add(h)
            passed, out = repro(cand)
            if passed:
                return cand, round(cost, 6), True
            failure = failure_summary(out)
            best_cand, best_diff = cand, _diff_cap(task.buggy, cand)
            failed_patches.append(best_diff or "(no-op patch)")
        if rnd < rounds - 1 and best_diff:        # MAR-lite critic between rounds
            try:
                diagnosis, it, ot = _llm(model_id, _CRITIC.format(
                    issue=task.issue_title, focus=focus, diff=best_diff, failure=failure),
                    temperature=0.2)
                cost += it * rate[0] + ot * rate[1]
            except Exception:  # noqa: BLE001
                diagnosis = ""
    return best_cand, round(cost, 6), ran
