# ruff: noqa: E501
"""Max-capability mode — verifier-gated ensemble/search over diverse agents (2605.14163, 2402.08147).

A single agent's ceiling is P(correct in one try). This router captures the UNION of N *diverse*
attempts (different provider × harness × thinking, so failures are uncorrelated) and selects the
correct one with an independent verifier — exceeding any single agent, bounded by verifier quality.
Operating point: spend up to a budget to MAXIMISE verified success (not minimise cost).

This module is callback-based (no eval/model deps): the caller supplies `run_arm_fn(arm)->Candidate`
and `verify_fn(candidates)->{arm: proxy_pass}`. It drives arms cheapest-first within budget, stops as
soon as a proxy-verified candidate appears, and reports the **any-correct oracle ceiling** (did any
attempt truly solve it) so the fraction the verifier captured is visible and honest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Candidate:
    arm: str
    public_pass: bool
    hidden_pass: bool          # held-out truth — for MEASUREMENT only, never used to select/stop
    cost: float
    workspace: Any = None      # opaque handle the verifier understands (e.g. a path)
    diff: str = ""


@dataclass
class EnsembleResult:
    solved: bool               # the SELECTED candidate's true verdict
    selected_arm: str | None
    any_correct: bool          # oracle ceiling: did ANY run arm actually solve it
    n_arms_run: int
    total_cost: float
    terminal: str              # proxy_verified | budget_exhausted | arms_exhausted
    arm_path: list[str] = field(default_factory=list)
    selected_proxy_pass: bool = False


RunArmFn = Callable[[str], Candidate]
VerifyFn = Callable[[list[Candidate]], dict[str, bool]]   # arm -> proxy_pass over the candidates so far


def solve_ensemble(*, arms: list[str], run_arm_fn: RunArmFn, verify_fn: VerifyFn,
                   budget: float, select_fn: Callable[[list[Candidate], dict[str, bool]], Candidate | None] | None = None
                   ) -> EnsembleResult:
    """Run diverse arms cheapest-first within `budget`; stop at the first proxy-verified candidate.

    `verify_fn` is re-run over ALL candidates so far so it can use cross-agent consensus (agreement
    among diverse arms is itself a strong signal). The held-out `hidden_pass` is recorded but never
    consulted for selection/stopping — only the proxy decides.
    """
    ran: list[Candidate] = []
    spent = 0.0
    path: list[str] = []
    for arm in arms:
        if spent > budget:
            return _finalize(ran, verify_fn, spent, path, "budget_exhausted", select_fn)
        c = run_arm_fn(arm)
        ran.append(c)
        spent += c.cost
        path.append(arm)
        proxy = verify_fn(ran)
        chosen = (select_fn or _default_select)(ran, proxy)
        if chosen is not None and proxy.get(chosen.arm, False):
            return EnsembleResult(
                solved=chosen.hidden_pass, selected_arm=chosen.arm,
                any_correct=any(r.hidden_pass for r in ran), n_arms_run=len(ran),
                total_cost=round(spent, 6), terminal="proxy_verified", arm_path=path,
                selected_proxy_pass=True)
    return _finalize(ran, verify_fn, spent, path, "arms_exhausted", select_fn)


def _default_select(ran: list[Candidate], proxy: dict[str, bool]) -> Candidate | None:
    """Prefer a proxy-verified candidate (smallest diff as tie-break); else first public-pass; else first."""
    verified = [c for c in ran if proxy.get(c.arm, False)]
    if verified:
        return min(verified, key=lambda c: (len(c.diff) or 10**9, c.arm))
    return next((c for c in ran if c.public_pass), ran[0] if ran else None)


def _finalize(ran, verify_fn, spent, path, terminal, select_fn) -> EnsembleResult:
    proxy = verify_fn(ran) if ran else {}
    chosen = (select_fn or _default_select)(ran, proxy) if ran else None
    return EnsembleResult(
        solved=bool(chosen and chosen.hidden_pass), selected_arm=chosen.arm if chosen else None,
        any_correct=any(r.hidden_pass for r in ran), n_arms_run=len(ran),
        total_cost=round(spent, 6), terminal=terminal, arm_path=path,
        selected_proxy_pass=bool(chosen and proxy.get(chosen.arm, False)))


def oracle_capture_rate(results: list[EnsembleResult]) -> dict:
    """Across tasks: how much of the any-correct ceiling did the verifier actually capture?"""
    n = len(results)
    solved = sum(int(r.solved) for r in results)
    ceiling = sum(int(r.any_correct) for r in results)
    return {"n": n, "verified_solved": solved, "any_correct_ceiling": ceiling,
            "verifier_capture_rate": round(solved / ceiling, 4) if ceiling else None,
            "headroom_left": ceiling - solved}
