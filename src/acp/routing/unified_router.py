# ruff: noqa: E501
"""Unified router — one entrypoint that jointly chooses lever + escalates + remembers (Phase 2).

The project had strong parts in isolation: an escalation controller (`topology_program_executor`),
FinOps marginal-value gating (`finops/marginal_value`), and long-lived memory (`memory/experience_bank`)
— but nothing composed them, and memory was never queried by a routing decision. This is the single
`route_and_solve` that does:

  1. MEMORY recall — drop ladder rungs known to FAIL this failure-signature (so we start at the
     cheapest rung that isn't known-bad) and confirm a known-good rung; this is what makes cost per
     verified success DECLINE over sessions (a stateless agent can't do it).
  2. FINOPS trim — keep a rung only while its expected marginal value is positive within the budget
     class (don't pay for a rung whose uplift can't clear its cost).
  3. ESCALATE via `run_controller` — reuse its hard safety invariants (high-risk strict-verify,
     forbidden-file guard, route-to-human, never blind auto-approve). The injected `attempt_fn`
     reports `solved` = PROXY-verified (independent_proof), not public-only.
  4. MEMORY write — record which rung solved (positive) and which cheaper rungs failed (negative),
     so next time the failers are skipped.

Standalone: this does not touch the production `orchestration/runner.py`; it is proven on the eval
corpora and is callable by the runner when desired.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.finops.marginal_value import budget_for, marginal_value_of_next_call
from acp.memory.experience_bank import ExperienceBank, ExperienceEpisode
from acp.memory.memory_policy import MemoryPolicy
from acp.routing.topology_program_executor import AttemptFn, run_controller

_CONTROL_ACTIONS = {"run_strict_verifier", "commit_success", "route_to_human", "abstain"}


@dataclass
class Lever:
    name: str               # also the memory `context_strategy` key
    est_cost: float         # expected $ for the FinOps gate
    prior_p_solve: float    # base success prior for the FinOps uplift


@dataclass
class UnifiedResult:
    task: str
    solved: bool
    terminal: str
    lever_path: list[str] = field(default_factory=list)
    total_cost: float = 0.0
    used_memory_seed: bool = False
    avoided: list[str] = field(default_factory=list)
    ladder_used: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"task": self.task, "solved": self.solved, "terminal": self.terminal,
                "lever_path": self.lever_path, "total_cost": round(self.total_cost, 6),
                "used_memory_seed": self.used_memory_seed, "avoided": self.avoided,
                "ladder_used": self.ladder_used, "safety_notes": self.safety_notes}


def _memory_reorder(ladder: list[Lever], *, memory: ExperienceBank | None, tenant: str,
                    failure_signature: str, recommend_fn=None, avoid_fn=None
                    ) -> tuple[list[Lever], list[str], bool]:
    """Drop rungs known to FAIL this signature (cheapest-first order otherwise preserved).

    `recommend_fn(bank, tenant=, failure_signature=)` / `avoid_fn(...)` override the bank's default
    "ever-failed" logic — e.g. aging-aware recency scoring (memory_revision) so a rung can be
    re-used after old failures age out.
    """
    if memory is None:
        return ladder, [], False
    _avoid = avoid_fn or (lambda bank, **kw: bank.avoid_strategies(**kw))
    _rec = recommend_fn or (lambda bank, **kw: bank.recommend_strategy(**kw))
    avoid = _avoid(memory, tenant=tenant, failure_signature=failure_signature)
    rec = _rec(memory, tenant=tenant, failure_signature=failure_signature)
    kept = [lev for lev in ladder if lev.name not in avoid or lev.name == rec]
    if not kept:  # everything avoided -> keep the recommended, else the full ladder (no worse off)
        kept = [lev for lev in ladder if lev.name == rec] or ladder
    return kept, sorted(avoid), bool(avoid or rec)


def _finops_trim(ladder: list[Lever], *, budget_class: str) -> list[Lever]:
    """Keep a rung only while its expected marginal value is positive within the budget envelope."""
    out: list[Lever] = []
    p_now = 0.0
    spend = 0.0
    for lev in ladder:
        p_after = max(p_now, lev.prior_p_solve)
        dec = marginal_value_of_next_call(p_success_now=p_now, p_success_after=p_after,
                                          call_cost=lev.est_cost, budget_class=budget_class,
                                          spend_so_far=spend)
        if dec.proceed:
            out.append(lev)
            spend += lev.est_cost
            p_now = p_after
    return out or ladder[:1]  # always keep at least one attempt


def _winning_and_failed(action_path: list[str], solved: bool) -> tuple[str | None, list[str]]:
    real = [a for a in action_path if a not in _CONTROL_ACTIONS]
    if solved and real:
        return real[-1], real[:-1]          # last real action solved; earlier ones failed
    return None, real                        # nothing solved -> all attempted rungs failed


def route_and_solve(*, task_id: str, failure_signature: str, repo_family: str, tenant: str,
                    task_type: str, risk_level: str, budget_class: str, ladder: list[Lever],
                    attempt_fn: AttemptFn, memory: ExperienceBank | None = None,
                    memory_policy: MemoryPolicy | None = None, now: float = 0.0,
                    recommend_fn=None, avoid_fn=None) -> UnifiedResult:
    """Route one task through memory-seeded, FinOps-gated, safety-bounded escalation; then learn."""
    ordered, avoided, seeded = _memory_reorder(
        ladder, memory=memory, tenant=tenant, failure_signature=failure_signature,
        recommend_fn=recommend_fn, avoid_fn=avoid_fn)
    trimmed = _finops_trim(ordered, budget_class=budget_class)
    res = run_controller(task_id, attempt_fn, risk_level=risk_level,
                         budget=budget_for(budget_class),
                         ladder=tuple(lev.name for lev in trimmed))
    winner, failed = _winning_and_failed(res.action_path, res.solved)
    if memory is not None and memory_policy is not None:
        if winner is not None:
            memory.write(_episode(repo_family, task_type, failure_signature, winner, tenant,
                                  outcome="solved", reward=1.0, cost=res.total_cost, now=now),
                         policy=memory_policy)
        for rung in failed:
            memory.write(_episode(repo_family, task_type, failure_signature, rung, tenant,
                                  outcome="failed", reward=-0.2, cost=0.0, now=now),
                         policy=memory_policy)
    return UnifiedResult(task=task_id, solved=res.solved, terminal=res.terminal,
                         lever_path=res.action_path, total_cost=res.total_cost,
                         used_memory_seed=seeded, avoided=avoided,
                         ladder_used=[lev.name for lev in trimmed], safety_notes=res.safety_notes)


def _episode(repo_family, task_type, failure_signature, strategy, tenant, *, outcome, reward,
             cost, now) -> ExperienceEpisode:
    return ExperienceEpisode(
        repo_family=repo_family, task_type=task_type, failure_signature=failure_signature,
        context_strategy=strategy, agent="unified_router", topology="escalation",
        verifier_outcome=outcome, reward=reward, cost=cost, privacy_scope=tenant, created_at=now)
