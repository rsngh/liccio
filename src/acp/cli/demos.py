"""No-API demos (charter §20): bugfix, human-review, bandit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from git import Repo

from acp.api.service import AppService
from acp.routing.simulation import run_simulation

_FIXED_CALC = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('division by zero')\n"
    "    return a / b\n"
)
_BUGGY_CALC = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def divide(a, b):\n    if b == 0:\n        return 0  # bug\n    return a / b\n"
)
_TEST = "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"


def make_demo_repo(root: Path) -> str:
    """Create a git repo with the divide-by-zero bug; return its path."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "calculator.py").write_text(_BUGGY_CALC)
    (root / "test_calculator.py").write_text(_TEST)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    (root / "AGENTS.md").write_text(
        "# Instructions\nDivision by zero must raise ZeroDivisionError.\n"
    )
    repo = Repo.init(root)
    repo.config_writer().set_value("user", "name", "acp").release()
    repo.config_writer().set_value("user", "email", "acp@example.com").release()
    repo.index.add(["calculator.py", "test_calculator.py", "pyproject.toml", "AGENTS.md"])
    repo.index.commit("initial buggy version")
    return str(root)


def run_bugfix_demo(service: AppService, workdir: Path) -> dict[str, Any]:
    repo_path = make_demo_repo(workdir / "demo_repo")
    repo = service.create_repo("demo-buggy-app", repo_path, default_branch="master")
    task = service.create_task(
        repo.id,
        title="Fix divide by zero in calculator",
        body="divide() returns 0 on zero divisor; it must raise ZeroDivisionError.",
        acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"],
        metadata={"files": {"calculator.py": _FIXED_CALC}},
    )
    state = service.run_task(task.id)
    return {
        "task_id": task.id,
        "run_id": state.run_id,
        "status": state.status if isinstance(state.status, str) else state.status.value,
        "snapshot_id": state.snapshot_id,
        "context_pack_id": state.context_pack_id,
        "routing_decision_id": state.routing_decision_id,
        "attempt_ids": state.attempt_ids,
        "selected_attempt_id": state.selected_attempt_id,
        "evaluation_result_id": state.evaluation_result_id,
        "reward_event_id": state.reward_event_id,
        "trace_id": state.trace_id,
    }


def run_bandit_demo(rounds: int = 1000, seed: int = 1234) -> dict[str, Any]:
    res = run_simulation(rounds=rounds, seed=seed)
    return {
        "rounds": res.rounds,
        "policy_reward": round(res.policy_reward, 2),
        "random_reward": round(res.random_reward, 2),
        "regret": round(res.regret, 2),
        "beats_random": res.beats_random,
        "action_counts": res.action_counts,
    }
