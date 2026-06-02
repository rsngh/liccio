"""Offline policy evaluation from persisted logs (Alpha 6, WS3 acceptance)."""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.routing.bandit import SimulatedBanditPolicy


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'o.db'}",
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


def test_evaluate_policy_offline_from_logged_runs(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    svc.policy = SimulatedBanditPolicy(epsilon=0.3)  # explore so propensities vary
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    for i in range(6):
        task = svc.create_task(repo.id, f"Fix divide {i}", "zero divisor",
                              metadata={"files": {"calculator.py": fixed}})
        svc.run_task(task.id)

    report = svc.evaluate_policy_offline(target="supervised")
    assert report["n"] >= 3
    est = report["estimates"]
    # Every estimator + DR bootstrap CI is present.
    for key in ("ips", "snips", "clipped_ips", "dr"):
        assert key in est
        assert "ci_low" in est[key] and "ci_high" in est[key]
    assert "effective_sample_size" in est["diagnostics"]
    assert "improvement_vs_logged" in report

    # Random baseline is also evaluable and reports its own diagnostics.
    rnd = svc.evaluate_policy_offline(target="random")
    assert rnd["n"] == report["n"]

    # WS5: promotion gate runs end-to-end and returns a decision + conditions.
    gate = svc.policy_promotion_check(target="supervised")
    assert "promote" in gate and isinstance(gate["promote"], bool)
    assert gate["conditions"], "gate must report its conditions"
    if gate["promote"]:
        assert gate["canary_plan"] is not None

    # WS6: real-log OPE compares policies and gates on trust.
    real = svc.real_log_ope_report()
    assert real["n"] == report["n"]
    assert {"random", "greedy", "supervised"} <= set(real["policies"].keys())
    assert isinstance(real["trustworthy"], bool)
    if real["trustworthy"]:
        assert real["ranking_by_dr"]
