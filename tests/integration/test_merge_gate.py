"""Independent merge-gate (round-2 Block L / §tests-1).

One place that asserts the alpha invariants a reviewer cares about, without
trusting verbal claims.
"""

from __future__ import annotations

from pathlib import Path

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings

ROOT = Path(__file__).resolve().parents[2]
FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


def test_current_status_exists_and_no_overclaim() -> None:
    status = (ROOT / "CURRENT_STATUS.md").read_text()
    assert "local v0" in status.lower() or "alpha" in status.lower()
    # no bare "production-grade" claim anywhere user-facing (only negations allowed)
    for name in ("README.md", "FINAL_REPORT.md", "CURRENT_STATUS.md"):
        text = (ROOT / name).read_text().lower()
        for line in text.splitlines():
            if "production-grade" in line:
                assert any(neg in line for neg in ("not", "not yet", "v0", "alpha")), \
                    f"overclaim in {name}: {line}"


def test_full_run_graph_reconstructs_after_restart(tmp_path) -> None:
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'm.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )
    svc = AppService(settings)
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "m"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    repo.index.commit("init")
    r = svc.create_repo("m", str(src), default_branch="master")
    task = svc.create_task(r.id, "Fix divide bug", "zero divisor",
                           metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)

    fresh = AppService(settings)
    graph = fresh.full_run_graph(state.run_id)
    assert graph["attempts"] and graph["reward_events"] and graph["evaluation"]
    assert graph["spans"]


def test_migrations_apply_cleanly(tmp_path, monkeypatch) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from acp.core.config import reset_settings
    from acp.db.models import ALL_MODELS
    from acp.db.session import make_engine

    db = f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("ACP_DATABASE_URL", db)
    reset_settings()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "src/acp/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", db.replace("+aiosqlite", ""))
    command.upgrade(cfg, "head")
    tables = set(inspect(make_engine(db)).get_table_names())
    for model in ALL_MODELS:
        assert model.__tablename__ in tables
