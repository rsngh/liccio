"""Live no-patch agent bakeoff with the real OpenAI harness (round-3 R3-4)."""

from __future__ import annotations

import os

import pytest
from git import Repo

from acp.agents.openai_harness import OpenAIHarnessAdapter
from acp.agents.registry import AgentRegistry
from acp.api.service import AppService
from acp.core.config import ACPSettings, reset_settings
from acp.evaluation.bakeoff import run_no_patch_bakeoff

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="no OPENAI_API_KEY")
def test_openai_harness_solves_no_patch_bugfix(tmp_path) -> None:
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    reset_settings()
    reg = AgentRegistry()
    reg.register(OpenAIHarnessAdapter(max_steps=6))
    svc = AppService(
        ACPSettings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'l.db'}",
                    artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"),
        registry=reg,
    )
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "import pytest\nfrom calculator import divide\n\n\n"
        "def test_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "l"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = svc.create_repo("l", str(src), default_branch="master")

    report = run_no_patch_bakeoff(svc, repo.id, n=1)
    cell = report["cells"][0]
    # the real LLM agent solved the bug with no supplied patch + captured a trace
    assert cell["solved_without_patch"] is True
    assert cell["tool_calls"] >= 1
    assert "calculator.py" in cell["file_writes"]
