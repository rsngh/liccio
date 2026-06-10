# ruff: noqa: E501, C408
"""End-to-end compose: SolutionStore + unified_router rung-0 + ExperienceBank over a recurrence.

Proves the integrated "cost-down over sessions" story in code (not just the offline eval): session 1
discovers the fix via the agent ladder and the loop records it; session 2 (same bug recurs) is solved
by the solution-cache rung 0 at zero agent cost, and the ladder never runs.
"""

from __future__ import annotations

from acp.memory.experience_bank import ExperienceBank
from acp.memory.memory_policy import MemoryPolicy
from acp.memory.solution_store import SolutionStore
from acp.routing.unified_router import build_agent_ladder, make_agent_attempt_fn, route_and_solve

BUGGY = "def f():\n    return 0\n"
FIXED = "def f():\n    return 1\n"
LADDER = build_agent_ladder([("inproc", 0.02, 0.2), ("codex_cli", 0.12, 0.95)])


def test_recurrence_is_solved_by_cache_rung0_after_first_session_learns() -> None:
    store, mem, pol = SolutionStore(), ExperienceBank(), MemoryPolicy()
    sig, fam, tenant = "AssertionError:f", "acme/lib", "t"

    def replay_fn(_task_id):
        cand = store.replay(tenant=tenant, repo_family=fam, failure_signature=sig, buggy_module_src=BUGGY)
        return (cand == FIXED, 0.0) if cand is not None else None   # "verified" stand-in for the held-out test

    common = dict(failure_signature=sig, repo_family=fam, tenant=tenant, task_type="bugfix",
                  risk_level="low", budget_class="migration", ladder=LADDER,
                  memory=mem, memory_policy=pol, solution_replay_fn=replay_fn)

    # SESSION 1: cache empty -> escalate (inproc fails, codex solves), then the loop records the fix
    fn = make_agent_attempt_fn(LADDER, lambda agent, _t: (agent == "codex_cli", {"inproc": 0.02, "codex_cli": 0.12}[agent]))
    s1 = route_and_solve(task_id="t1", attempt_fn=fn, now=0.0, **common)
    assert s1.solved and "codex_cli" in s1.lever_path and "solution_cache" not in s1.ladder_used
    assert s1.total_cost > 0.0
    # the live loop's post-solve hook records the verified fix
    store.record(repo_family=fam, failure_signature=sig, module_path="m.py", fixed_module_src=FIXED,
                 function_names=("f",), buggy_module_src=BUGGY, tenant=tenant, verified=True)

    # SESSION 2: same bug recurs -> solution-cache rung 0 short-circuits the whole ladder at ~0 cost
    s2 = route_and_solve(task_id="t2", attempt_fn=fn, now=1.0, **common)
    assert s2.solved and s2.ladder_used == ["solution_cache"]
    assert "codex_cli" not in s2.lever_path and s2.total_cost == 0.0
    assert s2.total_cost < s1.total_cost     # cost dropped to zero on the recurrence

    # memory recorded both the session-1 escalation winner and the session-2 cache solve
    episodes = mem.read(tenant=tenant, failure_signature=sig)
    strategies = {e.context_strategy for e in episodes}
    assert "codex_cli" in strategies and "solution_cache" in strategies
