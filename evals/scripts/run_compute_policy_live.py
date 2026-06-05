"""Compute-escalation policy live bakeoff (Alpha 29).

Compares compute arms on the hard greedy-trap cohort and populates the spend ledger so the
policy's escalation decisions are grounded in measured marginal value:
- cheap_single: one blind weak-model shot (reps for a reliability estimate);
- cheap_best_of_k: k blind shots + execution selection;
- cheap_advisor: one shot; on failure a frontier advisor diagnoses and the executor retries.

Then for each task the policy picks an arm from measured single-shot reliability + the
ledger, and we report the per-arm cost/quality + the chosen arm. Writes
evals/reports/compute_policy_bakeoff.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import build_bench_repo
from acp.agents.hard_tasks import HARD_TASKS
from acp.agents.weak_model_candidates import (
    DEFAULT_WEAK_MODEL,
    best_of_k,
    cost_usd,
    openai_sampler,
    propose_module,
    verify_candidate,
)
from acp.core.config import get_settings
from acp.core.optional import try_import
from acp.observability.live_report import redact_report
from acp.orchestration.compute_policy import ComputeSpendLedger, arms_summary, choose_arm

EXEC = DEFAULT_WEAK_MODEL
ADVISOR = "gpt-4o"
REPS = 3
K = 6


def _verify_with_output(task, content) -> tuple[bool, str]:
    if content is None:
        return False, "no patch"
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)
        (repo / task.module_path).write_text(content)
        p = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo, capture_output=True,
                           text=True, timeout=60, check=False)
    return p.returncode == 0, (p.stdout or "")[-1200:]


def _advise(buggy: str, failure: str) -> tuple[str, float]:
    openai = try_import("openai")
    key = get_settings().openai_api_key
    if openai is None or key is None:
        return "", 0.0
    client = openai.OpenAI(api_key=key.get_secret_value(), max_retries=0)
    sys = ("You are a senior algorithm advisor. You cannot edit files. Given a buggy module "
           "and failing pytest output, name the algorithmic flaw and the correct approach in "
           "JSON {\"next_steps\": [\"...\"]}.")
    try:
        r = client.chat.completions.create(
            model=ADVISOR, temperature=0.2, timeout=60,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": f"MODULE:\n{buggy}\n\nFAILED:\n{failure}"}])
        u = r.usage
        steps = json.loads(r.choices[0].message.content or "{}").get("next_steps", [])
        return "\n".join(f"- {s}" for s in steps), cost_usd(
            ADVISOR, getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
    except Exception:  # noqa: BLE001
        return "", 0.0


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    sampler = openai_sampler(model=EXEC, temperature=0.9)
    ledger = ComputeSpendLedger()
    per_task = []
    for task in HARD_TASKS:
        # cheap_single (reps) -> reliability
        ss = [best_of_k(task, k=1, sampler=sampler, model=EXEC) for _ in range(REPS)]
        for r in ss:
            ledger.record("cheap_single", r.total_cost, r.solved)
        reliability = round(sum(r.solved for r in ss) / REPS, 4)
        # cheap_best_of_k
        bok = best_of_k(task, k=K, sampler=sampler, model=EXEC)
        ledger.record("cheap_best_of_k", bok.total_cost, bok.solved)
        # cheap_advisor: one shot, advisor on failure, retry
        p0 = propose_module(task, model=EXEC, temperature=0.5)
        solved, out = _verify_with_output(task, p0.content)
        adv_cost = p0.cost
        if not solved:
            guidance, c = _advise(task.buggy, out)
            adv_cost += c
            if guidance:
                p1 = propose_module(task, model=EXEC, temperature=0.2, extra_guidance=guidance)
                adv_cost += p1.cost
                solved = verify_candidate(task, p1).pytest_passed
        ledger.record("cheap_advisor", adv_cost, solved)
        decision = choose_arm(single_shot_reliability=reliability, risk="medium", value=0.6,
                              ledger=ledger)
        per_task.append({"task": task.name, "single_shot_reliability": reliability,
                         "best_of_k_solved": bok.solved, "advisor_solved": solved,
                         "policy_choice": decision.arm, "reason": decision.reason})
        print(f"{task.name:14s} reliability={reliability} best_of_k={bok.solved} "
              f"advisor={solved} -> policy={decision.arm}")

    summary = arms_summary(ledger)
    report = {"experiment": "compute_policy_bakeoff", "executor": EXEC, "advisor": ADVISOR,
              "arms": summary, "per_task": per_task,
              "best_of_k_marginal_positive": summary["cheap_best_of_k"]["marginal"].get("positive"),
              "advisor_marginal_positive": summary["cheap_advisor"]["marginal"].get("positive")}
    out_path = Path("evals/reports/compute_policy_bakeoff.json")
    out_path.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out_path.read_text(), f"{key} leaked!"
    print(f"\nbest_of_k marginal positive: {report['best_of_k_marginal_positive']} | "
          f"advisor marginal positive: {report['advisor_marginal_positive']}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
