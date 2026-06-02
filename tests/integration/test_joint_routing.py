"""Joint (agent × context-strategy) routing (Alpha 6, WS2).

Routing chooses both the agent and the context strategy, and the chosen strategy
must actually drive context compilation — the persisted ContextPack strategy
must equal the routed RoutingDecision strategy, even though context is initially
pre-compiled with a default strategy before routing runs.
"""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.routing.bandit import SimulatedBanditPolicy


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'j.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("c", str(src), default_branch="master")


def test_routed_strategy_drives_context_pack(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    # Force the bandit toward the "minimal" strategy arm so routing diverges from
    # the default pre-compiled strategy and the recompile path is exercised.
    svc.policy = SimulatedBanditPolicy(epsilon=0.0)
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": fixed}})
    state = svc.run_task(task.id)

    graph = svc.full_run_graph(state.run_id)
    decision = graph["routing_decision"]
    pack = graph["context_pack"]
    assert decision is not None and pack is not None
    # The context the agent received was compiled with the routed strategy.
    assert pack["strategy"] == decision["action"]["context_strategy"]
