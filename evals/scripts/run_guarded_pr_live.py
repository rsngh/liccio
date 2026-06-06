"""Guarded PR pipeline live demo (Alpha 32).

For each real-world repo-replay task: produce a draft patch live (gpt-4o-mini), verify it in
the sandbox, then build a DRAFT PR on a fresh feature branch (never a protected branch) with
a PR description + rollback plan. Proves: draft PRs are created in sandbox branches, zero
writes to protected branches, every applied PR has a rollback plan, unverified drafts are
blocked. Writes evals/reports/guarded_pr_live.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import build_bench_repo, run_pytest
from acp.agents.repo_replay import REPLAY_TASKS
from acp.agents.weak_model_candidates import DEFAULT_WEAK_MODEL, propose_module
from acp.core.config import get_settings
from acp.evaluation.evidence_quality import EvidenceTier, stamp_evidence
from acp.observability.live_report import redact_report
from acp.orchestration.guarded_pr import GuardedPRReport, build_draft_pr


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    report = GuardedPRReport()
    for task in REPLAY_TASKS:
        bench = task.as_bench_task()
        content = propose_module(bench, model=DEFAULT_WEAK_MODEL, temperature=0.3).content
        # verify the draft in an isolated sandbox before building the PR
        with tempfile.TemporaryDirectory() as d:
            vrepo = build_bench_repo(Path(d), bench)
            verified = False
            if content is not None:
                (vrepo / bench.module_path).write_text(content)
                verified = run_pytest(vrepo)
        # build the draft PR on a fresh feature branch in a separate sandbox clone
        with tempfile.TemporaryDirectory() as d2:
            prrepo = build_bench_repo(Path(d2), bench)
            base = subprocess.run(["git", "rev-parse", "master"], cwd=prrepo,
                                  capture_output=True, text=True, check=False).stdout.strip()
            pr = build_draft_pr(prrepo, task_id=task.name, issue_text=task.issue_text,
                                module_path=bench.module_path,
                                patch_content=content or "", verified=verified)
            master_after = subprocess.run(["git", "rev-parse", "master"], cwd=prrepo,
                                          capture_output=True, text=True,
                                          check=False).stdout.strip()
        report.n_tasks += 1
        report.n_draft_prs += int(pr.applied_to_branch)
        report.n_blocked_unverified += int(not verified)
        row = pr.to_dict()
        row["protected_branch_unchanged"] = master_after == base
        report.rows.append(row)
        print(f"{task.name:16s} verified={verified} pr_branch={pr.branch} "
              f"applied={pr.applied_to_branch} "
              f"protected_unchanged={row['protected_branch_unchanged']}")
    out_data = stamp_evidence({**report.to_dict(),
                               "all_protected_branches_unchanged":
                                   all(r["protected_branch_unchanged"] for r in report.rows)},
                              EvidenceTier.FIXTURE)
    out = Path("evals/reports/guarded_pr_live.json")
    out.write_text(json.dumps(redact_report(out_data), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"\ndraft_prs={report.n_draft_prs}/{report.n_tasks} "
          f"zero_protected_writes={out_data['zero_protected_branch_writes']} "
          f"all_protected_unchanged={out_data['all_protected_branches_unchanged']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
