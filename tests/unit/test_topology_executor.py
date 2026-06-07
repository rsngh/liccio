"""Executable topology controller tests (GOALS Alpha 44 P2)."""

from __future__ import annotations

from acp.routing.topology_program_executor import AttemptOutcome, run_controller


def _fn(outcomes):
    def attempt(action, task):
        return outcomes.get(action)
    return attempt


def test_escalation_solves_when_cheap_fails_but_grep_succeeds() -> None:
    # the hard cross-file pattern: cheap fails, grep verifies
    outs = {
        "cheap_single": AttemptOutcome(solved=False, public_solved=False, cost=0.002),
        "retry_with_grep": AttemptOutcome(solved=True, public_solved=True, cost=0.003),
    }
    r = run_controller("t", _fn(outs), risk_level="low", budget=0.05)
    assert r.solved and r.terminal == "commit_success"
    assert r.action_path == ["cheap_single", "retry_with_grep", "commit_success"]
    assert abs(r.total_cost - 0.005) < 1e-9


def test_stops_early_when_cheap_succeeds() -> None:
    outs = {"cheap_single": AttemptOutcome(solved=True, public_solved=True, cost=0.002)}
    r = run_controller("t", _fn(outs))
    assert r.action_path == ["cheap_single", "commit_success"]


def test_high_risk_requires_strict_verifier_before_commit() -> None:
    outs = {
        "cheap_single": AttemptOutcome(solved=True, public_solved=True, cost=0.002,
                                       security_relevant=True),
        "run_strict_verifier": AttemptOutcome(solved=False, public_solved=True, cost=0.001),
    }
    r = run_controller("t", _fn(outs), risk_level="high")
    # strict verifier failed -> not committed despite a hidden 'solve'
    assert not r.solved and "run_strict_verifier" in r.action_path
    assert r.terminal == "route_to_human"


def test_forbidden_file_candidate_never_committed() -> None:
    outs = {
        "cheap_single": AttemptOutcome(solved=True, public_solved=True, cost=0.002,
                                       touched_forbidden=True),
        "retry_with_grep": AttemptOutcome(solved=True, public_solved=True, cost=0.003),
    }
    r = run_controller("t", _fn(outs))
    assert r.solved and r.action_path[1] == "retry_with_grep"  # the forbidden one was skipped


def test_budget_exhaustion_routes_to_human() -> None:
    outs = {a: AttemptOutcome(solved=False, public_solved=False, cost=0.03)
            for a in ("cheap_single", "retry_with_grep", "retry_with_repo_map")}
    r = run_controller("t", _fn(outs), risk_level="low", budget=0.05)
    assert r.terminal == "route_to_human"


def test_unsolved_high_risk_never_blind_auto_approves() -> None:
    outs = {a: AttemptOutcome(solved=False, public_solved=True, cost=0.001)
            for a in ("cheap_single", "retry_with_grep", "retry_with_repo_map",
                      "ask_readonly_advisor")}
    r = run_controller("t", _fn(outs), risk_level="high", budget=1.0)
    assert not r.solved and r.terminal == "route_to_human"
