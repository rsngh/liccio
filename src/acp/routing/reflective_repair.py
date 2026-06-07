# ruff: noqa: E501
"""Verifier-guided reflective repair (Reflexion 2303.11366; VerMCTS 2402.08147).

When an attempt fails its checks, a single agent stops. A meta-router can do better: feed the failure
signal back and re-dispatch a *repair* attempt (optionally across a different arm), so success rises
above one-shot — bounded by depth + budget + verifier quality. These are the pure pieces: distil a
bounded failure summary from test output, and build a Reflexion-style repair prompt. The orchestration
(when to trigger, which arm) lives in the capability router / eval.
"""

from __future__ import annotations

import re

_KEEP = re.compile(r"(assert|Error|Exception|Traceback|FAILED|!=|==|expected|got)", re.I)


def failure_summary(test_output: str, *, max_lines: int = 8, max_chars: int = 800) -> str:
    """Distil the salient failure lines (assertions/errors) from pytest output, bounded."""
    lines = [ln.strip() for ln in (test_output or "").splitlines() if ln.strip()]
    salient = [ln for ln in lines if _KEEP.search(ln)]
    picked = (salient or lines)[-max_lines:]
    return "\n".join(picked)[-max_chars:]


def build_repair_prompt(*, issue_text: str, module_path: str, prior_code: str,
                        failure: str) -> str:
    """Reflexion-style repair prompt: reflect on WHY the prior attempt failed, then fix it."""
    return (
        "Your previous attempt to implement the task FAILED its tests. Reflect briefly on the most "
        "likely root cause, then return a corrected implementation.\n\n"
        f"TASK:\n{issue_text}\n\n"
        f"YOUR PREVIOUS `{module_path}` (failed):\n{prior_code[:2000]}\n\n"
        f"TEST FAILURE (what went wrong):\n{failure[:1000]}\n\n"
        "Return ONLY JSON {\"files\": {\"" + module_path + "\": \"full corrected content\"}}. "
        "Fix the actual cause; do not just restate the previous code."
    )


def should_repair(*, all_failed: bool, depth: int, max_depth: int, spent: float, budget: float) -> bool:
    """Trigger a repair wave only when every primary attempt failed and depth/budget remain."""
    return all_failed and depth < max_depth and spent < budget
