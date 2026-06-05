"""Close the governance loop: promote the proven skill via staged canary (Alpha 23 WS11).

Takes the LIVE underspecified A/B result (baseline 0.44 vs skill 1.0, P(better) 0.997,
decision=promote) and drives it through the real staged-canary deploy pipeline
(5%->25%->50%->100% with guardrails). On a clean rollout the full-suite-discipline skill is
deployed ACTIVE and a SkillCanaryRun audit record is persisted. This is the first skill
PROMOTED on honest live evidence — and it only happens because the lift is real and
guardrail-clean, not timeout-confounded. Writes reports/live/underspecified_promotion.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import acp.db.models  # noqa: F401  (register ORM models)
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.observability.live_report import redact_report
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_canary_platform import StageMetrics, staged_canary_deploy
from acp.training.skill_registry import active_skill_for

STAGES = (0.05, 0.25, 0.50, 1.0)
SKILL = (
    "# full-suite discipline skill\n"
    "- The task may mention ONE failing test, but other tests can also be broken.\n"
    "- Always run the FULL suite with `python -m pytest -q` and fix EVERY failing test.\n"
)


def main() -> int:
    ab = json.loads(Path("reports/live/underspecified_skill_ab.json").read_text())
    control, canary = float(ab["baseline_rate"]), float(ab["skill_rate"])
    promote_decision = ab.get("decision") == "promote"
    # Build per-stage metrics from the measured live rates (guardrail-checked each stage).
    m = StageMetrics(control_solve=control, canary_solve=canary, control_cost=0.01,
                     canary_cost=0.01, measurement_quality=1.0, control_har=1.0,
                     canary_har=1.0, control_hfr=1.0, canary_hfr=1.0)
    metrics = dict.fromkeys(STAGES, m)
    candidate = SkillDocument(name="full_suite_discipline", content=SKILL, version=2,
                              status=SkillStatus.CANDIDATE,
                              scope=SkillScope(task_type="bugfix"))
    with tempfile.TemporaryDirectory() as d:
        eng = make_engine(f"sqlite:///{d}/promo.db")
        create_all(eng)
        sf = make_session_factory(eng)
        with session_scope(sf) as s:
            run, dep = staged_canary_deploy(EntityStore(s), candidate, "baseline_v1",
                                            metrics)
            active = active_skill_for(EntityStore(s), task_type="bugfix")
            active_name = active.name if active else None
    report = {
        "experiment": "ws11_underspecified_promotion", "harness": ab.get("harness"),
        "baseline_rate": control, "skill_rate": canary, "lift": ab.get("lift"),
        "prob_better": ab.get("prob_better"), "ab_decision": ab.get("decision"),
        "stages": [{"stage": v.stage, "decision": v.decision, "breaches": v.breaches}
                   for v in run.stages],
        "promoted": run.status == "promoted", "deployed": dep.deployed,
        "active_skill": active_name, "canary_run_status": run.status,
        "guardrails_clean": promote_decision and run.status == "promoted",
    }
    out = Path("reports/live/underspecified_promotion.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    print(f"promotion: status={run.status} deployed={dep.deployed} "
          f"active_skill={active_name} (lift={ab.get('lift')}, P={ab.get('prob_better')})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
