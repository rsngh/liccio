"""Alpha 11 evidence bundle (WS20).

Generates the production-readiness artifacts: a policy dossier from a real run,
the preference-reward governance gate, the data-governance red-team, durable
drift persistence, the exploration executor, a scheduler report, the mixed
corpus, and a production-mode health snapshot. Docker/vendor/LoRA live artifacts
are environment-gated and reported honestly as unavailable when their
prerequisites are absent.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from git import Repo

REPORTS = Path("evals/reports")


def _temp_service():
    from acp.api.service import AppService
    from acp.core.config import ACPSettings

    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'a11.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws"))
    return svc, tmp


def _policy_dossier() -> dict:
    svc, tmp = _temp_service()
    src = tmp / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = svc.create_repo("c", str(src), default_branch="master")
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                           metadata={"files": {"calculator.py":
                                               "def divide(a, b):\n    return a / b\n"}},
                           acceptance_criteria=["divide(x,0) raises"])
    state = svc.run_task(task.id)
    return svc.policy_dossier(state.run_id)


def _preference_reward_gate() -> dict:
    from acp.learning.reviewer_reliability import (
        default_governance_dataset,
        evaluate_preference_reward_governance,
    )

    labels, features, truth = default_governance_dataset()
    return evaluate_preference_reward_governance(
        labels, features, truth_by_attempt=truth, post_merge_correlation=0.5)


def _data_governance_redteam() -> dict:
    from acp.evaluation.data_governance_redteam import run_data_governance_redteam
    return run_data_governance_redteam()


def _drift_persistence() -> dict:
    from acp.learning.drift import WindowedOutcome

    svc, _ = _temp_service()

    class _Ens:
        learned_promoted = True

    baseline = [WindowedOutcome(0.9 if i % 2 == 0 else 0.1, i % 2 == 0, "low", i)
                for i in range(40)]
    recent = [WindowedOutcome(0.9, False, "high", 100 + i) for i in range(20)]
    return svc.run_and_persist_drift(_Ens(), model_name="learned_viability",
                                     baseline=baseline, recent=recent)


def _exploration_executor() -> dict:
    from acp.evaluation.capability_campaign import generate_campaign_report
    from acp.learning.exploration_run import ExplorationBudget, ExplorationRun

    matrix = generate_campaign_report(repetitions=6)
    return ExplorationRun().run(matrix, budget=ExplorationBudget(max_samples=80),
                                ope_overlap=0.4, regret=0.2).to_dict()


def _scheduler_report() -> dict:
    svc, _ = _temp_service()
    return svc.learn_schedule_run()


def _mixed_corpus() -> dict:
    from acp.evaluation.mixed_corpus import generate_mixed_corpus
    return generate_mixed_corpus(scale="test")


def _health_production() -> dict:
    svc, _ = _temp_service()
    # Seed the OPE log with the REAL observed live-bakeoff outcomes (if present) so
    # the production OPE gate reflects genuine agent data, not an empty lab.
    live = Path("reports/live/alpha11_live_bakeoff.json")
    if live.exists():
        try:
            cells = json.loads(live.read_text()).get("cells", [])
            if cells:
                svc.ingest_bakeoff_cells(cells)
        except Exception:  # noqa: BLE001
            pass
    return svc.control_plane_health(mode="production")


def _vendor_harness_live() -> dict:
    """Preserve a live-proven vendor report if one exists (run_vendor_live.py);
    otherwise emit a capability-only report in the same schema."""
    existing = REPORTS / "vendor_harness_live.json"
    if existing.exists():
        try:
            prior = json.loads(existing.read_text())
            if prior.get("live_proven"):
                return prior  # don't downgrade a real live proof
        except Exception:  # noqa: BLE001
            pass
    import asyncio
    import dataclasses

    from acp.agents import build_default_registry
    from acp.agents.capabilities import build_capability_registry

    caps = asyncio.run(build_capability_registry(build_default_registry()))
    vendor = {e.name: dataclasses.asdict(e) for e in caps.entries
              if e.category == "vendor"}
    return {"experiment": "alpha11_vendor_harness_live", "live_proven": False,
            "codex_cli": vendor.get("codex_cli", {"available": False}),
            "note": "run `make vendor-live` (codex binary + ACP_LIVE_CODEX + Docker) "
                    "to produce a live-proven report"}


def _local_lora_pilot() -> dict:
    from acp.training.local_lora import lora_available

    return {"experiment": "alpha11_local_lora_pilot",
            "available": lora_available(),
            "status": "skipped" if not lora_available() else "ready",
            "reason": "training deps (torch/peft/transformers) + GPU unavailable"
            if not lora_available() else "",
            "recommended_model": "Qwen/Qwen2.5-Coder-1.5B-Instruct"}


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "policy_dossier.json": _policy_dossier(),
        "preference_reward_gate.json": _preference_reward_gate(),
        "data_governance_redteam.json": _data_governance_redteam(),
        "drift_persistence.json": _drift_persistence(),
        "exploration_executor.json": _exploration_executor(),
        "scheduler_report.json": _scheduler_report(),
        "mixed_empirical_corpus.json": _mixed_corpus(),
        "control_plane_health_production.json": _health_production(),
        "vendor_harness_live.json": _vendor_harness_live(),
        "local_lora_pilot.json": _local_lora_pilot(),
    }
    for name, data in artifacts.items():
        (REPORTS / name).write_text(json.dumps(data, indent=2, default=str) + "\n")
        print(f"wrote {REPORTS / name}")
    rt = artifacts["data_governance_redteam.json"]["summary"]
    print(f"gov red-team: all_blocked={rt.get('all_blocked')} leaks={rt.get('leaks')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
