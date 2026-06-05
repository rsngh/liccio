"""Training-data export artifacts for areas 10 + 12 (Alpha 24, offline).

Area 12 (tool-format): builds the RL-ready tool-use dataset with binary format/functional
rewards + a malformed-rate audit and a HAR/HFR activation summary.
Area 10 (workflow distillation): distills successful trajectories into a repo-disjoint
context-selector dataset with a memorization audit + a majority-class training smoke.
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.training.tool_format_dataset import (
    ToolCallRecord,
    build_tool_format_dataset,
    harness_activation_summary,
)
from acp.training.workflow_distillation import (
    Trajectory,
    build_distillation_dataset,
    small_model_smoke,
)

ROOT = Path("evals/reports")


def _tool_records() -> list[ToolCallRecord]:
    recs = []
    for i in range(20):
        wf = i % 7 != 0                      # ~14% malformed
        recs.append(ToolCallRecord("openai_harness", "write_file" if wf else "",
                                   {"path": f"f{i}.py"}, wf, wf and i % 3 != 0))
    for i in range(12):
        recs.append(ToolCallRecord("claude_code", "edit", {"path": f"g{i}.py"}, True,
                                   i % 4 != 0))
    return recs


def _trajectories() -> list[Trajectory]:
    out = []
    repos = ["repoA", "repoB", "repoC", "repoD"]
    for i in range(40):
        r = repos[i % len(repos)]
        ctx = "grep" if i % 3 else "hybrid"
        out.append(Trajectory("bugfix" if i % 2 else "refactor", r, float(i), ctx,
                              "logic_fix", "assertion", success=i % 5 != 0,
                              risk="high" if i % 9 == 0 else "low"))
    return out


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    tf = build_tool_format_dataset(_tool_records())
    (ROOT / "tool_format_dataset.json").write_text(json.dumps(tf.to_dict(), indent=2) + "\n")
    (ROOT / "harness_activation_training.json").write_text(
        json.dumps({"experiment": "harness_activation_training",
                    "by_adapter": harness_activation_summary(_tool_records())},
                   indent=2) + "\n")

    ds = build_distillation_dataset(_trajectories(), "context_selector",
                                    holdout_repos={"repoD"})
    (ROOT / "workflow_distillation_dataset.json").write_text(
        json.dumps({"experiment": "workflow_distillation_dataset", **ds.to_dict()},
                   indent=2) + "\n")
    (ROOT / "small_model_training_smoke.json").write_text(
        json.dumps({"experiment": "small_model_training_smoke", **small_model_smoke(ds)},
                   indent=2) + "\n")
    (ROOT / "memorization_audit.json").write_text(
        json.dumps({"experiment": "memorization_audit",
                    "memorization_overlap": ds.memorization_overlap,
                    "repo_disjoint": ds.repo_disjoint, "leakage_clean": ds.is_clean()},
                   indent=2) + "\n")
    for n in ("tool_format_dataset", "harness_activation_training",
              "workflow_distillation_dataset", "small_model_training_smoke",
              "memorization_audit"):
        print(f"wrote {ROOT / n}.json")
    print(f"tool malformed_rate={tf.malformed_rate} | distill clean={ds.is_clean()} "
          f"overlap={ds.memorization_overlap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
