"""Cross-harness transfer live mini-study (Alpha 22 WS18).

Measures whether a skill optimized under an ACP in-process harness transfers to the
vendor-native harnesses. The source lift is the validated R15 result (openai_harness weak
0.5 -> 1.0). The target measurement runs the smoke fixture through the vendor harness with
vs without the skill, conclusive attempts only, then classifies portability
(portable / harness-specific / negative / insufficient evidence). Writes
reports/live/cross_harness_vendor_transfer.json (redacted).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from acp.agents.vendor_native import VendorNativeHarness, build_smoke_fixture
from acp.evaluation.measurement_hygiene import build_hygiene_report
from acp.observability.live_report import redact_report
from acp.training.skill_transfer_study import TransferObservation, run_transfer_study

SKILL = ("# bugfix skill\n"
         "- After editing, run the project's tests and fix any failures before finishing.\n")
SOURCE_LIFT = 0.5          # validated R15 openai_harness weak lift (0.5 -> 1.0)
REPS = 3
# claude_code drives headlessly fast; codex is included only if a quick run is feasible.
TARGETS = ["claude_code"]


def _solve_rate(harness: VendorNativeHarness, skill: str | None) -> float:
    cells = []
    for _ in range(REPS):
        with tempfile.TemporaryDirectory() as d:
            repo = build_smoke_fixture(Path(d))
            cells.append(harness.run_smoke(repo, timeout_s=180,
                                           skill_content=skill).to_cell())
    rep = build_hygiene_report(cells)
    return rep.solve_rate if rep.n_conclusive else 0.0


def main() -> int:
    observations = []
    target_reports = {}
    for name in TARGETS:
        if shutil.which(VendorNativeHarness(name).spec.binary) is None:
            target_reports[name] = {"available": False}
            continue
        h = VendorNativeHarness(name)
        baseline = _solve_rate(h, None)
        with_skill = _solve_rate(h, SKILL)
        observations.append(TransferObservation(
            source_harness="openai_harness", target_harness=name,
            target_baseline=baseline, target_with_skill=with_skill,
            source_lift=SOURCE_LIFT))
        target_reports[name] = {"available": True, "baseline": baseline,
                                "with_skill": with_skill,
                                "gain": round(with_skill - baseline, 4)}

    study = run_transfer_study("bugfix_verify", observations)
    report = {
        "experiment": "ws18_cross_harness_vendor_transfer",
        "skill": SKILL, "source_harness": "openai_harness", "source_lift": SOURCE_LIFT,
        "targets": target_reports,
        "scope_recommendation": study.scope_recommendation,
        "verdicts": [{"target": v.target_harness, "transfer_gain": v.transfer_gain,
                      "portable": v.portable, "negative_transfer": v.negative_transfer,
                      "recommendation": v.recommendation} for v in study.verdicts],
    }
    out = Path("reports/live/cross_harness_vendor_transfer.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"cross-harness transfer: {report['scope_recommendation']}")
    for v in report["verdicts"]:
        print(f"  -> {v['target']}: gain={v['transfer_gain']} portable={v['portable']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
