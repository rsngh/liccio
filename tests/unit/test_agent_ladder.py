# ruff: noqa: E501, C408, E731
"""Agent-swap escalation ladder — offline tests (fake solve_fn; no network).

Exercises the P3 capability: a cheapest-first AGENT ladder (inproc -> gemini -> claude -> codex) that
climbs agents and stops at the first whose output verifies, and whose per-family memory makes the
known-good agent get seeded on a repeat (cost-per-verified-success declines). Solve patterns mirror
the real per-agent results in reports/issue_replay_routing_economics.json.
"""

from __future__ import annotations

from acp.memory.experience_bank import ExperienceBank
from acp.memory.memory_policy import MemoryPolicy
from acp.routing.unified_router import build_agent_ladder, make_agent_attempt_fn, route_and_solve

# cheapest-first, costs match the effective-cost prior used in the economics report
SPECS = [("inproc_repair", 0.02, 0.2), ("gemini_cli", 0.06, 0.85),
         ("claude_code", 0.10, 0.88), ("codex_cli", 0.12, 0.95)]
LADDER = build_agent_ladder(SPECS)


def _solve_fn(winners: set[str]):
    # produced cost is the rung's est_cost; an agent "produces a fix" iff it is a winner for this task
    cost = {a: c for a, c, _ in SPECS}
    return lambda agent, _tid: (agent in winners, cost[agent])


def test_climbs_agents_and_stops_at_first_that_verifies() -> None:
    # the real index-6 case: inproc & gemini miss, claude_code solves -> ladder escalates to claude, stops (codex never run)
    fn = make_agent_attempt_fn(LADDER, _solve_fn({"claude_code", "codex_cli"}))
    res = route_and_solve(task_id="b6", failure_signature="bugfix:boltons.iterutils", repo_family="boltons",
                          tenant="t", task_type="bugfix", risk_level="low", budget_class="migration",
                          ladder=LADDER, attempt_fn=fn, memory=None)
    assert res.solved and res.terminal == "commit_success"
    assert res.lever_path[:3] == ["inproc_repair", "gemini_cli", "claude_code"]
    assert "codex_cli" not in res.lever_path  # stopped before the strongest/most expensive agent


def test_verify_stop_overrides_an_agents_own_claim() -> None:
    # gemini CLAIMS success (produced) but its output fails the acceptance test -> ladder must not stop there
    produced = _solve_fn({"gemini_cli", "codex_cli"})           # gemini & codex produce
    verify = lambda agent, _tid: agent in {"codex_cli"}          # only codex actually verifies
    fn = make_agent_attempt_fn(LADDER, produced, verify_fn=verify)
    res = route_and_solve(task_id="b", failure_signature="bugfix:x", repo_family="r", tenant="t",
                          task_type="bugfix", risk_level="low", budget_class="migration",
                          ladder=LADDER, attempt_fn=fn, memory=None)
    assert res.solved and res.lever_path[-2] == "codex_cli"     # escalated past gemini's false claim


def test_family_memory_seeds_known_good_agent_and_cost_declines() -> None:
    mem, pol = ExperienceBank(), MemoryPolicy()
    fn = make_agent_attempt_fn(LADDER, _solve_fn({"gemini_cli", "claude_code", "codex_cli"}))
    common = dict(task_id="b", failure_signature="bugfix:boltons.dictutils", repo_family="boltons",
                  tenant="t", task_type="bugfix", risk_level="low", budget_class="migration",
                  ladder=LADDER, attempt_fn=fn, memory=mem, memory_policy=pol)
    s0 = route_and_solve(**common, now=0.0)
    s1 = route_and_solve(**common, now=1.0)
    # session 0 pays for the failing inproc rung first; session 1 skips it (memory learned the family's agent)
    assert "inproc_repair" in s0.lever_path
    assert "inproc_repair" not in s1.ladder_used and s1.used_memory_seed
    assert s1.total_cost < s0.total_cost and s1.solved


def test_solution_cache_rung0_short_circuits_the_ladder() -> None:
    # a verified cache replay solves at rung 0 -> no agent rung runs, near-zero cost
    fn = make_agent_attempt_fn(LADDER, _solve_fn({"codex_cli"}))  # would otherwise climb to codex
    res = route_and_solve(task_id="b", failure_signature="bugfix:recurring", repo_family="r", tenant="t",
                          task_type="bugfix", risk_level="low", budget_class="migration", ladder=LADDER,
                          attempt_fn=fn, memory=None, solution_replay_fn=lambda _t: (True, 0.0))
    assert res.solved and res.terminal == "commit_success"
    assert res.ladder_used == ["solution_cache"] and res.total_cost == 0.0
    assert "codex_cli" not in res.lever_path  # the expensive ladder never ran


def test_solution_cache_miss_falls_through_to_ladder() -> None:
    # cache miss (None) or unverified replay -> normal escalation proceeds unchanged
    fn = make_agent_attempt_fn(LADDER, _solve_fn({"gemini_cli", "codex_cli"}))
    res = route_and_solve(task_id="b", failure_signature="bugfix:x", repo_family="r", tenant="t",
                          task_type="bugfix", risk_level="low", budget_class="migration", ladder=LADDER,
                          attempt_fn=fn, memory=None, solution_replay_fn=lambda _t: None)
    assert res.solved and "gemini_cli" in res.lever_path and "solution_cache" not in res.ladder_used


def test_difficulty_prefilter_drops_doomed_cheap_rung() -> None:
    # probe predicts the cheap inproc rung is doomed -> drop it; ladder starts at gemini, saving inproc's cost
    fn = make_agent_attempt_fn(LADDER, _solve_fn({"gemini_cli", "claude_code", "codex_cli"}))
    res = route_and_solve(task_id="b", failure_signature="bugfix:hard", repo_family="r", tenant="t",
                          task_type="bugfix", risk_level="low", budget_class="migration", ladder=LADDER,
                          attempt_fn=fn, memory=None, drop_levers={"inproc_repair"})
    assert res.solved and "inproc_repair" not in res.ladder_used
    assert res.lever_path[0] == "gemini_cli"   # started at the first non-dropped rung


def test_difficulty_prefilter_never_empties_the_ladder() -> None:
    # pathological: probe tries to drop everything -> keep at least one rung (never abstain by mistake)
    fn = make_agent_attempt_fn(LADDER, _solve_fn({"inproc_repair", "gemini_cli", "claude_code", "codex_cli"}))
    res = route_and_solve(task_id="b", failure_signature="x", repo_family="r", tenant="t",
                          task_type="bugfix", risk_level="low", budget_class="migration", ladder=LADDER,
                          attempt_fn=fn, memory=None, drop_levers={lev.name for lev in LADDER})
    assert res.ladder_used and res.solved
