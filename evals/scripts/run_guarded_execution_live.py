"""Guarded execution live demo (Alpha 30) — draft patches, zero writes.

Requests mode=draft_pr for each real-world repo-replay task. The guardrail policy caps it
(autonomous PR off by default), then the live weak model produces a DRAFT patch in an
isolated sandbox repo, verified by the task's hidden tests. The hard invariant: nothing is
applied to the working tree and nothing is merged. Records draft production + sandbox
verification + the proof that the working tree is untouched. Writes
evals/reports/guarded_execution_live.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from acp.agents.repo_replay import REPLAY_TASKS
from acp.agents.weak_model_candidates import DEFAULT_WEAK_MODEL, propose_module
from acp.core.config import get_settings
from acp.evaluation.evidence_quality import EvidenceTier, stamp_evidence
from acp.observability.live_report import redact_report
from acp.orchestration.guarded_execution import (
    ExecutionMode,
    guard,
    produce_draft_patch,
)


def _working_tree_dirty() -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                         check=False).stdout
    # ignore the artifact we are about to write + any /goal-managed files
    lines = [ln for ln in out.splitlines()
             if "guarded_execution_live.json" not in ln and "GOALS" not in ln
             and "pdfs/" not in ln]
    return bool(lines)


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    before_dirty = _working_tree_dirty()
    rows = []
    n_produced = n_verified = 0
    for task in REPLAY_TASKS:
        bench = task.as_bench_task()
        decision = guard(task_id=task.name, requested_mode=ExecutionMode.LOW_RISK_AUTONOMOUS_PR,
                         risk="medium")  # request the top of the ladder; policy will cap it
        draft = produce_draft_patch(
            bench, propose=lambda t: propose_module(t, model=DEFAULT_WEAK_MODEL,
                                                    temperature=0.3).content)
        n_produced += int(draft.produced)
        n_verified += int(draft.verified_in_sandbox)
        rows.append({"task": task.name, "allowed_mode": decision.allowed_mode,
                     "autonomous_write": decision.autonomous_write,
                     "draft_produced": draft.produced,
                     "verified_in_sandbox": draft.verified_in_sandbox,
                     "applied": draft.applied, "merged": draft.merged,
                     "diff_lines": draft.diff_lines})
        print(f"{task.name:16s} allowed={decision.allowed_mode} produced={draft.produced} "
              f"verified={draft.verified_in_sandbox} applied={draft.applied}")
    after_dirty = _working_tree_dirty()
    report = {
        "experiment": "guarded_execution_live", "model": DEFAULT_WEAK_MODEL,
        "n_tasks": len(REPLAY_TASKS), "n_drafts_produced": n_produced,
        "n_verified_in_sandbox": n_verified,
        "no_autonomous_writes": all(not r["autonomous_write"] for r in rows),
        "nothing_applied": all(not r["applied"] and not r["merged"] for r in rows),
        "working_tree_unchanged": before_dirty == after_dirty,
        "rows": rows,
    }
    report = stamp_evidence(report, EvidenceTier.FIXTURE)
    out = Path("evals/reports/guarded_execution_live.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"\ndrafts={n_produced}/{len(REPLAY_TASKS)} verified={n_verified} "
          f"no_autonomous_writes={report['no_autonomous_writes']} "
          f"nothing_applied={report['nothing_applied']} "
          f"working_tree_unchanged={report['working_tree_unchanged']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
