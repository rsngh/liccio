"""Alpha 9 evidence bundle (WS1).

Generates the deterministic Alpha-9 artifacts exercising the new decision-system
modules: Pareto routing under each profile, drift→demote, preference learning,
counterfactual regret, and a control-plane health snapshot.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

REPORTS = Path("evals/reports")


def _pareto_routing() -> dict:
    from acp.core.enums import AgentKind
    from acp.routing.pareto_policy import PROFILES, ParetoRoutingPolicy
    from acp.schemas.routing import RoutingAction

    cands = [
        RoutingAction(agent_kind=AgentKind.CLAUDE, agent_name="claude_harness",
                      context_strategy="test_focused", max_cost_usd=2.0),
        RoutingAction(agent_kind=AgentKind.FAKE, agent_name="fake",
                      context_strategy="minimal", max_cost_usd=0.1),
    ]
    feats = {"task_type": "bugfix", "risk_level": "medium"}
    choices = {}
    for name in PROFILES:
        dec = ParetoRoutingPolicy(profile=PROFILES[name]).choose_action(feats, cands)
        choices[name] = {"chosen": dec.action.agent_name,
                         "scores": dec.candidate_scores,
                         "reason": dec.exploration_reason}
    return {"experiment": "alpha9_pareto_routing", "profiles": sorted(PROFILES),
            "choices": choices}


def _drift_demote() -> dict:
    from acp.learning.drift import AutoDemoter, WindowedOutcome, detect_drift

    baseline = [WindowedOutcome(0.9 if i % 2 == 0 else 0.1, i % 2 == 0, "low", i)
                for i in range(40)]
    # Recent window: predictions stay confident but realizations flip -> accuracy drop.
    recent = [WindowedOutcome(0.9, False, "high", 100 + i) for i in range(20)]
    report = detect_drift(baseline, recent)

    class _Ens:
        learned_promoted = True
    ens = _Ens()
    demoted = AutoDemoter().apply(ens, report)
    return {"experiment": "alpha9_drift_demote", "report": report.as_dict(),
            "demoted": demoted, "now_advisory": not ens.learned_promoted}


def _preference_learning() -> dict:
    from acp.learning.preference import (
        PreferenceModel,
        default_preference_dataset,
        evaluate_preference_model,
        pairs_from_labels,
    )

    labels, feats = default_preference_dataset()
    prefs = pairs_from_labels(labels, feats)
    model = PreferenceModel()
    model.fit(prefs)
    return {"experiment": "alpha9_preference_learning", "n_pairs": len(prefs),
            "evaluation": evaluate_preference_model(model, prefs)}


def _counterfactual_regret() -> dict:
    from acp.routing.counterfactual import total_regret, what_if
    from acp.routing.ope import OPESample

    cands = ["good", "bad"]
    log = [OPESample("ctx", "good" if i % 2 == 0 else "bad", 0.5,
                     1.0 if i % 2 == 0 else 0.0, cands) for i in range(40)]
    return {"experiment": "alpha9_counterfactual_regret",
            "total_regret": total_regret(log),
            "example_what_if": what_if(log, "ctx", "bad", cands).as_dict()}


def _control_plane_health() -> dict:
    from acp.api.service import AppService
    from acp.core.config import ACPSettings

    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'h.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws"))
    return svc.control_plane_health()


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "pareto_routing.json": _pareto_routing(),
        "drift_demote.json": _drift_demote(),
        "preference_learning.json": _preference_learning(),
        "counterfactual_regret.json": _counterfactual_regret(),
        "control_plane_health.json": _control_plane_health(),
    }
    for name, data in artifacts.items():
        (REPORTS / name).write_text(json.dumps(data, indent=2, default=str) + "\n")
        print(f"wrote {REPORTS / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
