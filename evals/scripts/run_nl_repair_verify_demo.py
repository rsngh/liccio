"""One bounded, end-to-end NL -> generate -> verify -> REPAIR -> verify -> guarded PR run.

A single real-world-shaped task carried through the entire ACP loop, live:

  1. NL ISSUE      a bug report that names ONE defect (deposit) but the repo also has a
                   second, UNMENTIONED defect (overdraft) caught only by a HIDDEN test.
  2. GENERATE      a cheap executor writes a full corrected module, BLIND to the tests.
  3. VERIFY        ACP's real sandbox verifier (build_bench_repo + hidden pytest) runs.
                   The blind fix repairs deposit but not overdraft -> verification FAILS.
  4. REPAIR        ACP's real escalation gate (consult_advisor) fires on the repeated
                   failure; a frontier advisor (no file access) reads the failing pytest
                   output, diagnoses the remaining defect, and returns typed next_steps;
                   the executor retries once with that guidance.
  5. VERIFY        the sandbox verifier runs again -> both hidden tests PASS.
  6. GUARDED PR    ACP's real guarded executor commits the VERIFIED fix to a fresh
                   acp/draft-* branch (never a protected branch) with a PR description
                   and a rollback plan. The protected branch is provably untouched.

Models are Claude (OpenAI is firewalled in this environment); every other moving part is
ACP's own machinery. Output is redacted + secret-scanned. Writes
evals/reports/nl_repair_verify_demo.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import UNDERSPECIFIED_TASKS, build_bench_repo
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
from acp.orchestration.guarded_pr import PROTECTED_BRANCHES, build_draft_pr

EXECUTOR = "claude-haiku-4-5-20251001"   # cheap worker
ADVISOR = "claude-opus-4-8"              # frontier diagnostician (advice only, no tools)

# A real bug report: it names ONLY the deposit defect. The overdraft defect is real but
# unmentioned, and is exercised only by a hidden test -> the blind first fix will miss it.
ISSUE = ("Account.deposit does not increase the balance: after a.deposit(100) the balance "
         "is still 0. Please fix the deposit bug.")

_EXEC_SYS = (
    "You are a precise bugfix engine. You are given a buggy Python module and a bug report. "
    'Return ONLY a JSON object {"module": "<full corrected file content>"} — the COMPLETE '
    "corrected source of the module file, nothing else."
)
_ADV_SYS = (
    "You are a senior engineering ADVISOR. You CANNOT edit files or run tools. Given a buggy "
    "module and a failing pytest output, diagnose what is STILL wrong and return ONLY JSON "
    '{"recommendation": "revise_plan", "next_steps": ["..."], "risk": "low|medium|high", '
    '"confidence": 0.0}. next_steps must name every remaining defect concretely.'
)


def _client():
    anthropic = try_import("anthropic")
    key = get_settings().anthropic_api_key
    if anthropic is None or key is None:
        return None
    return anthropic.Anthropic(api_key=key.get_secret_value(), max_retries=0)


def _ask_json(client, model: str, system: str, user: str) -> dict:
    msg = client.messages.create(
        model=model, max_tokens=2000, system=system,
        messages=[{"role": "user", "content": user + '\n\nReturn ONLY the JSON object.'}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].removeprefix("json").strip()
    return json.loads(text)


def _generate(client, buggy: str, module_path: str, guidance: str = "") -> str | None:
    """Blind generation: sees the buggy module + the issue, NEVER the hidden tests."""
    user = f"Module path: {module_path}\n\n=== BUGGY MODULE ===\n{buggy}\n\nISSUE: {ISSUE}"
    if guidance.strip():
        user += f"\n\n=== ADVISOR GUIDANCE (follow this) ===\n{guidance}"
    try:
        return _ask_json(client, EXECUTOR, _EXEC_SYS, user).get("module")
    except Exception as exc:  # noqa: BLE001
        print(f"  [generate error] {str(exc)[:120]}")
        return None


def _verify(task, content: str | None) -> tuple[bool, str]:
    """ACP's real sandbox verifier: buggy repo + hidden tests, candidate applied to MODULE."""
    if content is None:
        return False, "no patch produced"
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)
        (repo / task.module_path).write_text(content)
        proc = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo,
                              capture_output=True, text=True, timeout=60, check=False)
    return proc.returncode == 0, (proc.stdout or "")[-1500:]


def _advisor_fn(client, buggy: str):
    def _fn(call: AdvisorCall) -> AdvisorResponse:
        user = (f"=== BUGGY MODULE ===\n{buggy}\n\n=== FAILING PYTEST OUTPUT ===\n"
                f"{call.evidence_summary}\n\nDiagnose every remaining defect and advise.")
        try:
            data = _ask_json(client, ADVISOR, _ADV_SYS, user)
        except Exception as exc:  # noqa: BLE001
            print(f"  [advisor error] {str(exc)[:120]}")
            return AdvisorResponse(recommendation="continue", confidence=0.0)
        rec = data.get("recommendation", "revise_plan")
        rec = rec if rec in ("continue", "revise_plan", "run_test", "stop", "escalate") \
            else "revise_plan"
        return AdvisorResponse(recommendation=rec, next_steps=data.get("next_steps", []),
                               risk=data.get("risk", "medium"),
                               confidence=float(data.get("confidence", 0.5)))
    return _fn


def main() -> int:
    # Throwaway sandbox repos must not invoke the environment's commit-signing hook;
    # scope the override to subprocesses via env (never touches global git config).
    os.environ.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign",
                       "GIT_CONFIG_VALUE_0": "false"})
    client = _client()
    if client is None:
        print("[skip] ACP_ANTHROPIC_API_KEY not set")
        return 0
    task = next(t for t in UNDERSPECIFIED_TASKS if t.name == "bank")  # deposit + overdraft

    timeline: list[dict] = []
    print(f"TASK: {task.name}  (issue names 1 bug; hidden tests check 2)\n")

    # --- 1+2: NL issue -> blind generation -----------------------------------------------
    print("[1] generate (blind) ...")
    patch0 = _generate(client, task.buggy, task.module_path)
    # --- 3: verify -> expected FAIL (overdraft test unmentioned in the issue) ------------
    passed0, out0 = _verify(task, patch0)
    fail_line = next((ln for ln in out0.splitlines() if "passed" in ln or "failed" in ln), "")
    print(f"[3] verify first attempt: {'PASS' if passed0 else 'FAIL'}  ({fail_line.strip()})")
    timeline.append({"step": "generate+verify", "attempt": 1, "verified": passed0,
                     "pytest_summary": fail_line.strip()})

    # --- 4: REPAIR via ACP's real escalation gate ----------------------------------------
    advisor_fired = False
    next_steps: list = []
    passed1, patch1 = passed0, patch0
    if not passed0:
        state = ExecutorState(task_name=task.name, difficulty=task.difficulty, risk="medium",
                              consecutive_failures=1, evidence_summary=out0)
        call = consult_advisor(state, advisor_fn=_advisor_fn(client, task.buggy),
                               budget=AdvisorBudget(max_calls=1))
        if call is not None and call.advisor_response is not None:
            advisor_fired = True
            next_steps = list(call.advisor_response.next_steps)
            print(f"[4] advisor fired (trigger={call.trigger}); next_steps:")
            for s in next_steps:
                print(f"      - {s}")
            guidance = "\n".join(f"- {s}" for s in next_steps)
            patch1 = _generate(client, task.buggy, task.module_path, guidance=guidance)
            # --- 5: re-verify ------------------------------------------------------------
            passed1, out1 = _verify(task, patch1)
            fl1 = next((ln for ln in out1.splitlines()
                        if "passed" in ln or "failed" in ln), "")
            print(f"[5] verify after repair: {'PASS' if passed1 else 'FAIL'}  ({fl1.strip()})")
            timeline.append({"step": "advisor_repair+verify", "attempt": 2,
                             "trigger": call.trigger, "next_steps": next_steps,
                             "verified": passed1, "pytest_summary": fl1.strip()})

    # --- 6: GUARDED PR (only a verified patch is allowed onto a branch) -------------------
    draft = None
    if patch1 is not None:
        with tempfile.TemporaryDirectory() as d:
            prrepo = build_bench_repo(Path(d), task)  # has master as default branch
            base = subprocess.run(["git", "rev-parse", "master"], cwd=prrepo,
                                  capture_output=True, text=True, check=False).stdout.strip()
            pr = build_draft_pr(prrepo, task_id=task.name, issue_text=ISSUE,
                                module_path=task.module_path, patch_content=patch1,
                                verified=passed1)
            after = subprocess.run(["git", "rev-parse", "master"], cwd=prrepo,
                                   capture_output=True, text=True, check=False).stdout.strip()
        draft = pr.to_dict()
        draft["protected_branch_unchanged"] = after == base
        print(f"\n[6] guarded PR: branch={pr.branch} applied={pr.applied_to_branch} "
              f"protected_unchanged={draft['protected_branch_unchanged']}")
        if pr.blocked_reason:
            print(f"      blocked_reason: {pr.blocked_reason}")

    solved_only_after_repair = (not passed0) and bool(passed1)
    report = {
        "experiment": "nl_repair_verify_demo",
        "task": task.name,
        "issue": ISSUE,
        "hidden_tests": task.test_src,
        "executor_model": EXECUTOR,
        "advisor_model": ADVISOR,
        "first_attempt_verified": passed0,
        "advisor_fired": advisor_fired,
        "advisor_next_steps": next_steps,
        "final_verified": bool(passed1),
        "solved_only_after_repair": solved_only_after_repair,
        "draft_pr": draft,
        "branch_is_protected": (draft or {}).get("branch", "").split("/")[-1]
        in PROTECTED_BRANCHES,
        "protected_branch_unchanged": (draft or {}).get("protected_branch_unchanged"),
        "timeline": timeline,
        "final_module": patch1,
    }
    out = Path("evals/reports/nl_repair_verify_demo.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"\nsolved_only_after_repair={solved_only_after_repair}  "
          f"final_verified={bool(passed1)}  "
          f"protected_branch_unchanged={report['protected_branch_unchanged']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
