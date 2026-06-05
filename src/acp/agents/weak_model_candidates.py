"""Weak-model best-of-k candidate generation + execution comparator (Alpha 24 area 2).

Thesis (Weak-Model Critic-Comparator): orchestration quality, not only model size, drives
coding-agent outcomes — a cheap model sampled k times and selected by an EXECUTION proof
signal can rival a frontier single shot. This module samples k candidate fixes from a weak
model for a graded-benchmark task, verifies each by running the task's pytest suite in an
isolated repo, and selects the best by proof signal + diff minimality.

Safety / measurement-trust:
- The comparator only ever uses CONCLUSIVE attempts (a candidate whose verification ran).
  API/infra errors make a candidate inconclusive; they never count as capability failures.
- The model proposes ONLY the module file; the canonical test file is rewritten from the
  task each time, so a candidate can never pass by deleting or weakening tests.
- Cost is tracked per candidate so a cost-per-conclusive-success curve can be built.
"""

from __future__ import annotations

import difflib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from acp.agents.benchmark_suite import BenchTask, build_bench_repo, run_pytest

DEFAULT_WEAK_MODEL = "gpt-4o-mini"
# $/1k tokens (mirrors harness_base.COST_PER_1K; kept local to avoid import cycles).
_COST_PER_1K = {"gpt-4o-mini": 0.0006, "gpt-4o": 0.0075, "gpt-5-nano": 0.0004}
_DEFAULT_COST_PER_1K = 0.002

_SYS = ("You are a precise bugfix engine. You are given a buggy Python module and its "
        "failing tests. Return ONLY a JSON object {\"module\": \"<full corrected file "
        "content>\"} — the COMPLETE corrected source of the module file, nothing else. "
        "Do not modify or reference the tests; fix the module so all tests pass.")


def cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    rate = _COST_PER_1K.get(model, _DEFAULT_COST_PER_1K)
    return round((in_tok + out_tok) / 1000.0 * rate, 6)


@dataclass
class CandidatePatch:
    index: int
    content: str | None       # proposed full module content (None on API/infra error)
    in_tokens: int = 0
    out_tokens: int = 0
    cost: float = 0.0
    error: str | None = None


@dataclass
class CandidateVerification:
    index: int
    applied: bool
    pytest_passed: bool
    conclusive: bool          # verification actually ran (vs API/infra error)
    diff_lines: int
    cost: float
    error: str | None = None


@dataclass
class BestOfKResult:
    task_name: str
    difficulty: str
    k: int
    model: str
    solved: bool                       # >=1 candidate passed pytest
    best_index: int | None
    n_conclusive: int
    n_passed: int
    diversity: float                   # distinct candidate contents / k
    total_cost: float
    best_diff_lines: int | None
    outcome: str                       # AttemptOutcome value
    candidates: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["candidates"] = [dict(c.__dict__) for c in self.candidates]
        return d


def _diff_lines(before: str, after: str) -> int:
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="")
    return sum(1 for ln in diff if ln and ln[0] in "+-" and not ln.startswith(("+++", "---")))


def verify_candidate(task: BenchTask, patch: CandidatePatch) -> CandidateVerification:
    """Apply ``patch`` to a fresh repo and run the task's tests (execution proof signal)."""
    if patch.content is None:
        return CandidateVerification(index=patch.index, applied=False, pytest_passed=False,
                                     conclusive=False, diff_lines=0, cost=patch.cost,
                                     error=patch.error or "no content")
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)              # canonical buggy module + tests
        (repo / task.module_path).write_text(patch.content)  # apply candidate to MODULE only
        try:
            passed = run_pytest(repo, timeout_s=60)
            conclusive = True
            err = None
        except Exception as exc:  # noqa: BLE001  (pytest infra error -> inconclusive)
            passed, conclusive, err = False, False, str(exc)[:160]
    return CandidateVerification(
        index=patch.index, applied=True, pytest_passed=passed, conclusive=conclusive,
        diff_lines=_diff_lines(task.buggy, patch.content), cost=patch.cost, error=err)


def select_best(verifs: list[CandidateVerification]) -> int | None:
    """Execution comparator: prefer a passing candidate, tiebreak on diff minimality."""
    passing = [v for v in verifs if v.pytest_passed and v.conclusive]
    if passing:
        return min(passing, key=lambda v: (v.diff_lines, v.index)).index
    return None


def _classify(n_conclusive: int, n_passed: int) -> str:
    if n_conclusive == 0:
        return "infra_timeout_before_action"   # all candidates infra/API-failed
    if n_passed > 0:
        return "task_success"
    return "task_failure"


# A sampler maps (task, candidate_index) -> CandidatePatch. Injected for tests; the live
# path uses :func:`openai_sampler`.
Sampler = Callable[[BenchTask, int], CandidatePatch]


def best_of_k(task: BenchTask, *, k: int, sampler: Sampler,
              model: str = DEFAULT_WEAK_MODEL) -> BestOfKResult:
    """Sample k candidate fixes, verify each by execution, and select the best."""
    patches = [sampler(task, i) for i in range(k)]
    verifs = [verify_candidate(task, p) for p in patches]
    best = select_best(verifs)
    n_conclusive = sum(1 for v in verifs if v.conclusive)
    n_passed = sum(1 for v in verifs if v.pytest_passed and v.conclusive)
    distinct = len({p.content for p in patches if p.content is not None})
    return BestOfKResult(
        task_name=task.name, difficulty=task.difficulty, k=k, model=model,
        solved=n_passed > 0, best_index=best, n_conclusive=n_conclusive, n_passed=n_passed,
        diversity=round(distinct / k, 4) if k else 0.0,
        total_cost=round(sum(p.cost for p in patches), 6),
        best_diff_lines=(verifs[best].diff_lines if best is not None else None),
        outcome=_classify(n_conclusive, n_passed), candidates=verifs)


def openai_sampler(*, model: str = DEFAULT_WEAK_MODEL, temperature: float = 0.7,
                   timeout_s: float = 60.0) -> Sampler:
    """Build a live sampler that calls a weak OpenAI model for a full corrected module."""
    import json

    from acp.core.config import get_settings
    from acp.core.optional import try_import

    def _sample(task: BenchTask, index: int) -> CandidatePatch:
        openai = try_import("openai")
        key = get_settings().openai_api_key
        if openai is None or key is None:
            return CandidatePatch(index=index, content=None, error="openai unavailable")
        client = openai.OpenAI(api_key=key.get_secret_value(), max_retries=0)
        user = (f"Module path: {task.module_path}\n\n=== BUGGY MODULE ===\n{task.buggy}\n\n"
                f"=== TESTS ===\n{task.test_src}\n\n{task.prompt}")
        try:
            resp = client.chat.completions.create(
                model=model, temperature=temperature, timeout=timeout_s,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _SYS},
                          {"role": "user", "content": user}])
        except Exception as exc:  # noqa: BLE001  (API error -> inconclusive candidate)
            return CandidatePatch(index=index, content=None, error=str(exc)[:160])
        usage = resp.usage
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0
        try:
            content = json.loads(resp.choices[0].message.content or "{}").get("module")
        except Exception as exc:  # noqa: BLE001
            return CandidatePatch(index=index, content=None, in_tokens=in_tok,
                                  out_tokens=out_tok, cost=cost_usd(model, in_tok, out_tok),
                                  error=f"unparseable: {str(exc)[:80]}")
        return CandidatePatch(index=index, content=content, in_tokens=in_tok,
                              out_tokens=out_tok, cost=cost_usd(model, in_tok, out_tok))

    return _sample
