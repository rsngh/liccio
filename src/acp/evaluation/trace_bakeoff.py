"""Multi-adapter trace bakeoff (round-3 R3-5).

Runs the SAME task / repo / context compiler / verifier through several adapters
and compares their normalized AgentTraces — the foundation of the "real agent
traces" moat. Each adapter runs in its own AppService (own registry) on a fresh
copy of the repo so they don't interfere.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from git import Repo

ZERO_TEST = (
    "import pytest\nfrom calculator import divide\n\n\n"
    "def test_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n"
)


def make_bug_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (root / "test_calculator.py").write_text(ZERO_TEST)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "tb"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    repo = Repo.init(root)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    repo.index.commit("init")


def run_trace_bakeoff(adapter_factories: dict[str, Callable[[], object]]) -> dict:
    """For each named adapter factory, run the same no-patch bugfix and collect
    its normalized trace + outcome."""
    from acp.agents.registry import AgentRegistry
    from acp.api.service import AppService
    from acp.core.config import ACPSettings

    results: dict[str, dict] = {}
    for name, factory in adapter_factories.items():
        tmp = Path(tempfile.mkdtemp())
        reg = AgentRegistry()
        reg.register(factory())  # type: ignore[arg-type]
        svc = AppService(ACPSettings(
            database_url=f"sqlite+aiosqlite:///{tmp / 'tb.db'}",
            artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
            # Bakeoff harnesses run locally on purpose; opt in to the override so
            # the execution-backend policy permits them (audited per attempt).
            allow_local_harness=True,
        ), registry=reg)
        make_bug_repo(tmp / "repo")
        repo = svc.create_repo("tb", str(tmp / "repo"), default_branch="master")
        task = svc.create_task(repo.id, "Fix divide by zero",
                               "divide() must raise ZeroDivisionError. No patch supplied.",
                               acceptance_criteria=["raises ZeroDivisionError"], metadata={})
        state = svc.run_task(task.id)
        status = state.status if isinstance(state.status, str) else state.status.value
        runner = svc._runners.get(state.run_id)
        traces = getattr(runner.artifacts, "agent_traces", []) if runner else []
        tr = traces[0] if traces else None
        results[name] = {
            "status": status,
            "is_harness": tr.is_harness if tr else False,
            "tool_calls": tr.tool_calls if tr else 0,
            "commands": tr.commands if tr else 0,
            "file_writes": tr.file_writes if tr else [],
            "input_tokens": tr.input_tokens if tr else 0,
            "output_tokens": tr.output_tokens if tr else 0,
            "estimated_cost_usd": tr.estimated_cost_usd if tr else 0.0,
            "solved": status == "succeeded",
        }
    return {
        "adapters": results,
        "summary": {
            "n_adapters": len(results),
            "solved": [n for n, r in results.items() if r["solved"]],
            "harness_adapters": [n for n, r in results.items() if r["is_harness"]],
        },
    }
