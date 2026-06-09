# ruff: noqa: E501
"""Localized repair harness (Agentless / Kimi-Dev decomposition) — GOALS P3 enhancement.

The generic tool-loop harness failed on real bugs because it re-sent the whole 38-44 KB module
every step (~300K tokens / 16 steps) and never converged. All three research sweeps converged on
the same fix: DON'T put the whole file in context. This implements the decomposed pipeline the
papers recommend:

  1. LOCALIZE — run the failing test, and from the traceback + the failing test body + the issue
     title, pick the specific function/method(s) at fault (lexical/grep-style, no embeddings).
  2. REPAIR (best-of-k) — prompt the model with ONLY the focus function(s) + the precise failure
     (assertion/expected-vs-got), sampling k candidates; splice each corrected function back into
     the full module by AST span (so output is tiny, not a 40 KB rewrite).
  3. VERIFY + SELECT — run the repro test on each candidate; keep the first that passes (a
     deterministic "stochastic->deterministic boundary"). On total failure, do one bounded
     reflexion round feeding the closest candidate's failure back.

Context per call is ~1-3 KB (one function + failure) instead of 40 KB, steps are bounded, and
test-time compute (k samples) replaces a long serial thrash. Grading is unchanged (the pristine
hidden test runs against the produced module), so localization/splicing can't game the score.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

from evals.issue_replay.replay_task import IssueReplayTask

from acp.routing.reflective_repair import failure_summary

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def _run(repo: Path, test_name: str) -> tuple[bool, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        test_name, "-v"], cwd=repo, capture_output=True, text=True, timeout=90,
                       check=False, env=env)
    return p.returncode == 0, (p.stdout + "\n" + p.stderr)


def _func_table(module_src: str) -> dict[str, tuple[int, int, int]]:
    """name -> (start_line, end_line, indent) for every def/async-def (incl. methods), 1-based."""
    out: dict[str, tuple[int, int, int]] = {}
    try:
        tree = ast.parse(module_src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
            out[node.name] = (start, node.end_lineno or node.lineno, node.col_offset)
    return out


def _failed_tests(output: str) -> list[str]:
    return re.findall(r"(\w+)\s+FAILED|FAILED\s+\S+::(\w+)", output)  # type: ignore[return-value]


def _localize(module_src: str, issue_title: str, test_src: str, output: str) -> list[str]:
    """Rank the module's own defs by relevance to the bug and return the top 3 (or [] if none).

    Score = strong bonus if the def name appears in the issue title (commit subject usually names
    the fixed symbol, e.g. ``human_readable_list`` / ``OneToOne.update``) + how often it is CALLED
    in the failing test body (attribute calls ``obj.method(`` count too). Ranking by score — not
    file order — is what keeps the actually-buggy method from being dropped by the top-k cap."""
    from collections import Counter
    table = _func_table(module_src)
    if not table:
        return []
    failed = {a or b for a, b in _failed_tests(output)}
    bodies = ""
    try:
        ttree = ast.parse(test_src)
        for n in ast.walk(ttree):
            if isinstance(n, ast.FunctionDef) and (not failed or n.name in failed):
                bodies += "\n" + (ast.get_source_segment(test_src, n) or "")
    except SyntaxError:
        bodies = test_src
    title_ids = set(re.findall(r"[A-Za-z_]\w*", issue_title))
    called = Counter(re.findall(r"\.?([A-Za-z_]\w*)\s*\(", bodies))   # foo(...) and obj.method(...)
    scored = [(name, (10 if name in title_ids else 0) + called.get(name, 0))
              for name in table if not name.startswith("test")]
    scored = sorted((c for c in scored if c[1] > 0), key=lambda x: (-x[1], x[0]))
    return [name for name, _ in scored[:3]]


def _extract(module_src: str, names: list[str], table: dict[str, tuple[int, int, int]]) -> str:
    lines = module_src.splitlines()
    chunks = []
    for n in names:
        s, e, _ = table[n]
        chunks.append("\n".join(lines[s - 1:e]))
    return "\n\n".join(chunks)


def _splice(module_src: str, table: dict[str, tuple[int, int, int]], new: dict[str, str]) -> str:
    lines = module_src.splitlines()
    for name in sorted(new, key=lambda n: table.get(n, (0,))[0], reverse=True):
        if name not in table:
            continue
        s, e, indent = table[name]
        block = new[name].splitlines()
        # strip common leading indent from the model block, then re-indent to the original
        nonblank = [ln for ln in block if ln.strip()]
        common = min((len(ln) - len(ln.lstrip()) for ln in nonblank), default=0)
        reindented = [((" " * indent) + ln[common:]) if ln.strip() else "" for ln in block]
        lines[s - 1:e] = reindented
    return "\n".join(lines) + "\n"


def _parse_funcs(block: str) -> dict[str, str]:
    """Extract {func_name: source} from a returned code block (tolerates ``` fences)."""
    if "```" in block:
        parts = block.split("```")
        block = max((p[6:] if p.startswith("python") else p for p in parts[1::2]),
                    key=len, default=block)
    try:
        tree = ast.parse(block)
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            seg = ast.get_source_segment(block, node)
            if seg:
                out[node.name] = seg
    return out


def _llm(model_id: str, prompt: str, temperature: float) -> tuple[str, int, int]:
    if model_id.startswith("gemini"):
        import httpx
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("ACP_GEMINI_API_KEY")
        r = httpx.post(_ENDPOINT.format(m=model_id), params={"key": key},
                       json={"contents": [{"parts": [{"text": prompt}]}],
                             "generationConfig": {"maxOutputTokens": 4096, "temperature": temperature,
                                                  "thinkingConfig": {"thinkingBudget": 0}}}, timeout=120)
        d = r.json()
        cand = (d.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
        u = d.get("usageMetadata", {})
        return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    import anthropic
    c = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ACP_ANTHROPIC_API_KEY"))
    m = c.messages.create(model=model_id, max_tokens=4096, temperature=temperature,
                          messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in m.content if getattr(b, "type", "") == "text")
    return text, m.usage.input_tokens, m.usage.output_tokens


_PROMPT = (
    "You are fixing a bug in a Python module. {instr}\n\n"
    "ISSUE: {issue}\n\nCODE (the suspected buggy region):\n```python\n{focus}\n```\n\n"
    "{failure}"
)


def repair_one(task: IssueReplayTask, root: Path, *, model_id: str, rate: tuple[float, float],
               k: int = 3, max_rounds: int = 2) -> tuple[str, float, bool]:
    """Localized best-of-k repair. Returns (produced_module_src, cost_usd, ran)."""
    work = root / f"rp_{abs(hash(task.repo_name + task.issue_title)) % 10000}"
    work.mkdir(parents=True, exist_ok=True)
    for p, c in task.extra_files.items():
        (work / p).write_text(c)
    (work / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    (work / "test_repro.py").write_text(task.hidden_test)

    def repro(module_src: str) -> tuple[bool, str]:
        (work / task.module_path).write_text(module_src)
        return _run(work, "test_repro.py")

    current = task.buggy
    _, output = repro(current)
    table = _func_table(current)
    focus_names = _localize(current, task.issue_title, task.hidden_test, output)
    # whole-module fallback when localization finds nothing — show the real code (capped), not the
    # file head, and ask for a full rewrite rather than a function splice.
    whole = not focus_names
    focus = _extract(current, focus_names, table) if focus_names else current[:16000]
    cost = 0.0
    ran = False
    failure = ""
    best_cand = current
    instr = ("Return ONLY the full corrected module in a ```python code block."
             if whole else
             "Return ONLY the corrected full definition(s) of the function(s) shown, in a "
             "```python code block — same names, same signatures, nothing else.")
    for rnd in range(max_rounds):
        fail_block = f"TEST FAILURE (fix the real cause):\n{failure}\n" if failure else ""
        prompt = _PROMPT.format(instr=instr, issue=f"{task.issue_title}\n{task.issue_body}",
                                focus=focus, failure=fail_block)
        for i in range(k):
            try:
                text, it, ot = _llm(model_id, prompt, temperature=0.0 if (rnd == 0 and i == 0) else 0.7)
            except Exception:  # noqa: BLE001
                continue
            ran = True
            cost += it * rate[0] + ot * rate[1]
            if whole:
                cand = _first_block(text) or current
            else:
                funcs = _parse_funcs(text)
                cand = _splice(current, table, funcs) if funcs else current
            passed, out = repro(cand)
            if passed:
                return cand, round(cost, 6), True
            failure = failure_summary(out)
            best_cand = cand  # keep last as the working draft for the next reflexion round
        current = best_cand
        table = _func_table(current)
        if not whole:
            focus = _extract(current, [n for n in focus_names if n in table], table)
    return current, round(cost, 6), ran


def _first_block(text: str) -> str | None:
    """Fallback: a whole-module code block if the model returned the full file instead of funcs."""
    if "```" in text:
        parts = text.split("```")
        body = max((p[6:] if p.startswith("python") else p for p in parts[1::2]), key=len, default="")
        return body if "def " in body else None
    return None
