"""Advisor rescues SYSTEMATIC failures where best-of-k can't (Alpha 29 / Alpha 30).

repo_replay_live showed gpt-4o-mini fails paginate + lru_cache 0/5 AND best-of-5 also fails
(systematic, not variance). This validates the compute policy's "low reliability -> advisor/
frontier" rule: a frontier advisor (gpt-4o) diagnoses the systematic flaw and the cheap
executor retries with that guidance. Arms on the failing tasks:
  - executor_only (gpt-4o-mini single shot)
  - executor + advisor (gpt-4o diagnosis -> retry)
  - frontier_single (gpt-4o direct)
Writes evals/reports/repo_replay_advisor.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import build_bench_repo
from acp.agents.repo_replay import REPLAY_TASKS
from acp.agents.weak_model_candidates import cost_usd, propose_module
from acp.core.config import get_settings
from acp.core.optional import try_import
from acp.evaluation.evidence_quality import EvidenceTier, stamp_evidence
from acp.observability.live_report import redact_report

EXEC = "gpt-4o-mini"
FRONTIER = "gpt-4o"
# the systematically-failing tasks from repo_replay_live
TARGETS = ["paginate", "lru_cache"]
REPS = 3


def _verify(task, content) -> tuple[bool, str]:
    if content is None:
        return False, "no patch"
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)
        (repo / task.module_path).write_text(content)
        p = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo, capture_output=True,
                           text=True, timeout=60, check=False)
    return p.returncode == 0, (p.stdout or "")[-1200:]


def _advise(buggy, failure):
    openai = try_import("openai")
    key = get_settings().openai_api_key
    client = openai.OpenAI(api_key=key.get_secret_value(), max_retries=0)
    sysmsg = ("You are a senior engineer ADVISOR. You cannot edit files. Given a buggy module "
              "and failing pytest output, name the exact flaw and the fix approach in JSON "
              "{\"next_steps\": [\"...\"]}.")
    try:
        r = client.chat.completions.create(
            model=FRONTIER, temperature=0.2, timeout=60,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sysmsg},
                      {"role": "user", "content": f"MODULE:\n{buggy}\n\nFAILED:\n{failure}"}])
        u = r.usage
        steps = json.loads(r.choices[0].message.content or "{}").get("next_steps", [])
        return "\n".join(f"- {s}" for s in steps), cost_usd(
            FRONTIER, getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
    except Exception:  # noqa: BLE001
        return "", 0.0


def _frontier_solve(task):
    return propose_module(task, model=FRONTIER, temperature=0.3)


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    tasks = [t.as_bench_task() for t in REPLAY_TASKS if t.name in TARGETS]
    arms = {"executor_only": 0, "executor_advisor": 0, "frontier_single": 0}
    totals = dict.fromkeys(arms, 0)
    rows = []
    for bench, meta in zip(tasks, [t for t in REPLAY_TASKS if t.name in TARGETS],
                           strict=False):
        for _ in range(REPS):
            # executor only
            p0 = propose_module(bench, model=EXEC, temperature=0.4)
            solved0, out = _verify(bench, p0.content)
            totals["executor_only"] += 1
            arms["executor_only"] += int(solved0)
            # executor + advisor (only meaningful when it first failed)
            solved1 = solved0
            if not solved0:
                guidance, _ = _advise(meta.buggy, out)
                p1 = propose_module(bench, model=EXEC, temperature=0.2,
                                    extra_guidance=guidance)
                solved1, _ = _verify(bench, p1.content)
            totals["executor_advisor"] += 1
            arms["executor_advisor"] += int(solved1)
            # frontier single
            pf = _frontier_solve(bench)
            solvedf, _ = _verify(bench, pf.content)
            totals["frontier_single"] += 1
            arms["frontier_single"] += int(solvedf)
        rows.append({"task": bench.name})
    rates = {k: round(arms[k] / totals[k], 4) if totals[k] else 0.0 for k in arms}
    report = {"experiment": "repo_replay_advisor", "targets": TARGETS, "reps": REPS,
              "executor": EXEC, "frontier": FRONTIER, "solve_rate_by_arm": rates,
              "advisor_rescues_systematic": rates["executor_advisor"] > rates["executor_only"],
              "frontier_rescues_systematic": rates["frontier_single"] > rates["executor_only"]}
    report = stamp_evidence(report, EvidenceTier.FIXTURE)
    out = Path("evals/reports/repo_replay_advisor.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"solve rate by arm: {rates}")
    print(f"advisor rescues systematic: {report['advisor_rescues_systematic']} | "
          f"frontier rescues: {report['frontier_rescues_systematic']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
