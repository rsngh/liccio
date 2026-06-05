"""Advisor escalation live bakeoff (Alpha 24 area 1).

Cheap executor (gpt-4o-mini) works blind on the underspecified tasks (prompt names one bug;
a second is unmentioned). When its patch fails the held-out tests, a frontier ADVISOR
(gpt-4o) — which cannot edit files, only diagnose — reads the failure and returns next
steps; the executor retries once with that guidance. We measure conclusive solve rate and
cost for: executor-only vs executor+advisor, plus advisor calls/task, and confirm the
advisor is NOT consulted on an easy task the executor already solves.

Writes evals/reports/advisor_policy.json, advisor_bakeoff.json, and
advisor_cost_quality_frontier.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS, UNDERSPECIFIED_TASKS, build_bench_repo
from acp.agents.weak_model_candidates import cost_usd, propose_module
from acp.core.config import get_settings
from acp.core.optional import try_import
from acp.observability.live_report import redact_report
from acp.orchestration.advisor import (
    AdvisorBudget,
    AdvisorCall,
    AdvisorResponse,
    ExecutorState,
    consult_advisor,
)

EXECUTOR = "gpt-4o-mini"
ADVISOR = "gpt-4o"
DIVIDE = next(t for t in BENCH_TASKS if t.name == "divide")
_ADV_SYS = ("You are a senior engineering ADVISOR. You CANNOT edit files or run tools. "
            "Given a buggy module and a failing pytest output, diagnose what is still wrong "
            "and return ONLY JSON {\"recommendation\": \"revise_plan\", \"next_steps\": "
            "[\"...\"], \"risk\": \"low|medium|high\", \"confidence\": 0.0}. next_steps must "
            "name every remaining defect concretely.")


def _verify(task, content) -> tuple[bool, str]:
    """Apply content, run the hidden tests, return (passed, truncated failure output)."""
    if content is None:
        return False, "no patch produced"
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)
        (repo / task.module_path).write_text(content)
        proc = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo,
                              capture_output=True, text=True, timeout=60, check=False)
    return proc.returncode == 0, (proc.stdout or "")[-1500:]


def _advisor_fn(buggy: str):
    def _fn(call: AdvisorCall) -> AdvisorResponse:
        openai = try_import("openai")
        key = get_settings().openai_api_key
        if openai is None or key is None:
            return AdvisorResponse(recommendation="continue", confidence=0.0)
        client = openai.OpenAI(api_key=key.get_secret_value(), max_retries=0)
        user = (f"=== BUGGY MODULE ===\n{buggy}\n\n=== FAILING PYTEST OUTPUT ===\n"
                f"{call.evidence_summary}\n\nDiagnose remaining defects and advise.")
        try:
            resp = client.chat.completions.create(
                model=ADVISOR, temperature=0.2, timeout=60,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _ADV_SYS},
                          {"role": "user", "content": user}])
            data = json.loads(resp.choices[0].message.content or "{}")
            u = resp.usage
            call.cost = cost_usd(ADVISOR, getattr(u, "prompt_tokens", 0) or 0,
                                 getattr(u, "completion_tokens", 0) or 0)
            rec = data.get("recommendation", "revise_plan")
            rec = rec if rec in ("continue", "revise_plan", "run_test", "stop", "escalate") \
                else "revise_plan"
            return AdvisorResponse(recommendation=rec, next_steps=data.get("next_steps", []),
                                   risk=data.get("risk", "medium"),
                                   confidence=float(data.get("confidence", 0.5)))
        except Exception:  # noqa: BLE001
            return AdvisorResponse(recommendation="continue", confidence=0.0)
    return _fn


# A disclosed handicap that makes a narrowly-scoped cheap worker STALL on underspecified
# tasks: it fixes only the named symptom and stops, leaving the second bug. This exposes the
# escalation mechanism (capable executors solve these single-shot, so the advisor never
# fires — see the un-handicapped arm). The handicap is dropped on the advisor-guided retry.
_HANDICAP = ("IMPORTANT: change ONLY the single function explicitly named in the task. Do "
             "NOT modify, inspect, or fix any other function, even if it looks wrong.")


def _run_arm(task, *, use_advisor: bool, handicap: bool = False) -> dict:
    p0 = propose_module(task, model=EXECUTOR, temperature=0.4,
                        extra_guidance=_HANDICAP if handicap else "")
    passed, out = _verify(task, p0.content)
    cost = p0.cost
    advisor_calls = 0
    if passed or not use_advisor:
        return {"task": task.name, "difficulty": task.difficulty, "solved": passed,
                "advisor_calls": advisor_calls, "cost": round(cost, 6),
                "conclusive": p0.content is not None}
    # executor stalled -> consult the frontier advisor (it only diagnoses)
    state = ExecutorState(task_name=task.name, difficulty=task.difficulty, risk="medium",
                          consecutive_failures=1, evidence_summary=out)
    budget = AdvisorBudget(max_calls=1)
    call = consult_advisor(state, advisor_fn=_advisor_fn(task.buggy), budget=budget)
    if call is not None and call.advisor_response is not None:
        advisor_calls = 1
        cost += call.cost
        guidance = "\n".join(f"- {s}" for s in call.advisor_response.next_steps)
        p1 = propose_module(task, model=EXECUTOR, temperature=0.2, extra_guidance=guidance)
        cost += p1.cost
        passed, _ = _verify(task, p1.content)
    return {"task": task.name, "difficulty": task.difficulty, "solved": passed,
            "advisor_calls": advisor_calls, "cost": round(cost, 6), "conclusive": True}


def _summary(rows: list[dict]) -> dict:
    conc = [r for r in rows if r["conclusive"]]
    solved = [r for r in conc if r["solved"]]
    cost = sum(r["cost"] for r in rows)
    return {"n": len(rows), "n_conclusive": len(conc), "n_solved": len(solved),
            "solve_rate": round(len(solved) / len(conc), 4) if conc else 0.0,
            "advisor_calls": sum(r["advisor_calls"] for r in rows),
            "total_cost": round(cost, 6),
            "cost_per_solved": round(cost / len(solved), 6) if solved else None}


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    base = [_run_arm(t, use_advisor=False) for t in UNDERSPECIFIED_TASKS]
    adv = [_run_arm(t, use_advisor=True) for t in UNDERSPECIFIED_TASKS]
    # Controlled handicapped-executor arms: forces a stall so the escalation fires.
    hbase = [_run_arm(t, use_advisor=False, handicap=True) for t in UNDERSPECIFIED_TASKS]
    hadv = [_run_arm(t, use_advisor=True, handicap=True) for t in UNDERSPECIFIED_TASKS]
    easy = _run_arm(DIVIDE, use_advisor=True)  # must NOT consult the advisor
    base_s, adv_s = _summary(base), _summary(adv)
    hbase_s, hadv_s = _summary(hbase), _summary(hadv)
    policy = {"experiment": "advisor_policy", "executor": EXECUTOR, "advisor": ADVISOR,
              "advisor_not_called_on_easy": easy["advisor_calls"] == 0,
              "advisor_not_called_when_executor_succeeds": adv_s["advisor_calls"] == 0,
              "triggers": ["repeated_test_failure", "high_risk", "low_confidence",
                           "verifier_disagreement", "ambiguous_spec"],
              "contract": "advisor cannot edit files or call tools; advice only"}
    bakeoff = {"experiment": "advisor_bakeoff", "executor": EXECUTOR, "advisor": ADVISOR,
               "executor_only": base_s, "executor_plus_advisor": adv_s,
               "lift": round(adv_s["solve_rate"] - base_s["solve_rate"], 4),
               "handicapped_executor_only": hbase_s,
               "handicapped_executor_plus_advisor": hadv_s,
               "handicapped_lift": round(hadv_s["solve_rate"] - hbase_s["solve_rate"], 4),
               "rows": {"executor_only": base, "executor_plus_advisor": adv,
                        "handicapped_executor_only": hbase,
                        "handicapped_executor_plus_advisor": hadv, "easy": easy}}
    frontier = {"experiment": "advisor_cost_quality_frontier", "points": [
        {"arm": "executor_only", "solve_rate": base_s["solve_rate"],
         "cost_per_solved": base_s["cost_per_solved"]},
        {"arm": "executor_plus_advisor", "solve_rate": adv_s["solve_rate"],
         "cost_per_solved": adv_s["cost_per_solved"]}]}
    for path, data in (("evals/reports/advisor_policy.json", policy),
                       ("evals/reports/advisor_bakeoff.json", bakeoff),
                       ("evals/reports/advisor_cost_quality_frontier.json", frontier)):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(redact_report(data), indent=2) + "\n")
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            secret = os.environ.get(key)
            if secret:
                assert secret not in out.read_text(), f"{key} leaked!"
    print(f"executor_only: solve={base_s['solve_rate']} cost/solved={base_s['cost_per_solved']}")
    print(f"executor+advisor: solve={adv_s['solve_rate']} advisor_calls={adv_s['advisor_calls']} "
          f"lift={bakeoff['lift']}")
    print(f"[handicapped] executor_only: solve={hbase_s['solve_rate']}")
    print(f"[handicapped] executor+advisor: solve={hadv_s['solve_rate']} "
          f"advisor_calls={hadv_s['advisor_calls']} lift={bakeoff['handicapped_lift']}")
    print(f"advisor NOT called on easy task: {policy['advisor_not_called_on_easy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
