"""Run a live multi-harness bakeoff and write REDACTED artifacts (round-5 WS2).

Requires OPENAI_API_KEY + ANTHROPIC_API_KEY (and the openai/anthropic SDKs).
Runs the OpenAI and Claude true harnesses on the same single no-patch bugfix,
then writes redacted, reviewable JSON to reports/live/:

    reports/live/live_openai_claude_bakeoff.json   (both adapters, redacted)
    reports/live/live_openai_harness.json          (openai cells slice)
    reports/live/live_claude_harness.json          (claude cells slice)

No secrets, prompts, file contents, diffs, or provider IDs are written.

    uv run python evals/scripts/redact_live_report.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from acp.observability.live_report import assert_no_secrets, redact_report

OUT = Path("reports/live")


def _have(mod: str, key: str) -> bool:
    try:
        __import__(mod)
    except Exception:
        return False
    return bool(os.environ.get(key))


def main() -> int:
    if not (_have("openai", "OPENAI_API_KEY") and _have("anthropic", "ANTHROPIC_API_KEY")):
        print("SKIP: needs OPENAI_API_KEY+openai and ANTHROPIC_API_KEY+anthropic")
        return 0
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    from acp.core.config import reset_settings
    reset_settings()

    from acp.evaluation.bakeoff_v2 import factory_for, run_bakeoff_v2
    from acp.evaluation.dataset import load_dataset

    # single bugfix task keeps the live run cheap; write a 1-task temp dataset
    tasks = [t for t in load_dataset("evals/datasets/no_patch_tasks.yaml")
             if t.key == "bugfix_divide_zero"]
    tmp = Path(tempfile.mkdtemp()) / "one_task.yaml"
    import yaml
    tmp.write_text(yaml.safe_dump({"tasks": [{
        "key": t.key, "task_type": t.task_type, "risk": t.risk, "fixture": t.fixture,
        "title": t.title, "body": t.body, "acceptance": t.acceptance,
        "expected_human_review": t.expected_human_review} for t in tasks]}))

    factories = {"openai_harness": factory_for("openai_harness"),
                 "claude_harness": factory_for("claude_harness")}
    report = run_bakeoff_v2(factories, tmp, repetitions=1, backend="local")
    redacted = redact_report(report)
    assert_no_secrets(redacted)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "live_openai_claude_bakeoff.json").write_text(json.dumps(redacted, indent=2))
    for adapter, fname in (("openai_harness", "live_openai_harness.json"),
                           ("claude_harness", "live_claude_harness.json")):
        slice_ = {**redacted,
                  "cells": [c for c in redacted["cells"] if c["adapter"] == adapter]}
        (OUT / fname).write_text(json.dumps(slice_, indent=2))

    solved = report["summary"]["solve_rate"]
    print(f"live bakeoff: adapters={sorted(factories)} solve_rate={solved} "
          f"-> wrote redacted artifacts to {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
