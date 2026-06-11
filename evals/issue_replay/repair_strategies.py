# ruff: noqa: E501
"""Failure-category -> repair-strategy directives (AutoVerus-style library, P7 W3).

AutoVerus's gain came from mapping verifier error categories to specialized regeneration strategies
instead of one generic "try again". Our verifier is the repair battery; its BatteryScore already
separates the failure modes. Each category maps to 2-4 concrete directives; the search round-robins
them across sibling expansions so children explore *different* repair hypotheses (expansion diversity),
not temperature noise alone.
"""

from __future__ import annotations

from acp.verification.repair_battery import BatteryScore

CATEGORIES = ("adversarial", "no_parse", "exception", "guard_regression",
              "discriminating_stuck", "wrong_value")


def categorize(score: BatteryScore | None, fail_detail: str = "") -> str:
    """Map a candidate's battery outcome to a failure category (deterministic, no LLM)."""
    if score is None:
        return "no_parse"
    if score.adversarial_high:
        return "adversarial"
    text = fail_detail or ""
    if any(t in text for t in ("Traceback", "TypeError", "AttributeError", "NameError",
                               "ImportError", "raised", "Error:")):
        return "exception"
    if score.guard_frac < 1.0 and score.disc_frac >= score.guard_frac:
        return "guard_regression"
    if score.disc_frac == 0.0:
        return "discriminating_stuck"
    return "wrong_value"


STRATEGIES: dict[str, list[str]] = {
    "adversarial": [
        "Do NOT modify, weaken or delete any test or assertion; fix ONLY the module code so the real behaviour changes.",
        "Remove any try/except added around the failing behaviour and fix the underlying cause instead of swallowing it.",
    ],
    "no_parse": [
        "Return ONLY syntactically valid Python: the complete corrected definition(s), nothing else, in one ```python block.",
        "Re-emit the full definition(s) with consistent indentation; do not truncate or elide bodies with '...'.",
    ],
    "exception": [
        "The patch crashes before behaviour can be judged. Fix the crash first: check argument counts, None handling, attribute names and imports against the API map.",
        "Trace the exception line: the failing call's types do not match. Make the minimal change that restores a runnable module, then address the behaviour.",
    ],
    "guard_regression": [
        "Your change broke behaviour the buggy code already got right. Make the SMALLEST possible change; do not touch code paths the passing checks exercise.",
        "Restore the original behaviour for all inputs not implicated by the issue; condition the new behaviour narrowly on the case the issue describes.",
        "Diff your patch mentally against the original: revert every change that is not strictly required to fix the issue.",
    ],
    "discriminating_stuck": [
        "The bug is NOT yet fixed: every failing check still fails. Identify the exact expression those checks exercise and change its LOGIC (operator, boundary, ordering), not formatting or naming.",
        "Take a different hypothesis from all failed patches: consider off-by-one bounds (< vs <=), empty/identical-input cases, mutation vs copy, and lazy vs eager evaluation.",
        "Walk one failing check's input through the code line by line; find the first line where actual diverges from expected and fix that line.",
        "Re-read the issue title literally — it usually names the exact symbol and condition that must change.",
    ],
    "wrong_value": [
        "Close: some checks now pass. For each still-failing check, compute the expected value by hand from the spec and adjust the computation to produce exactly it.",
        "Check operator precedence, rounding, inclusive/exclusive boundaries and sign in the expression the failing checks exercise.",
        "Your fix handles the main case; add the missing edge case (empty, single element, equal endpoints, zero) the failing checks describe.",
    ],
}


def directive(category: str, i: int) -> str:
    """The i-th strategy directive for a category (round-robins for sibling-expansion diversity)."""
    opts = STRATEGIES.get(category) or STRATEGIES["discriminating_stuck"]
    return opts[i % len(opts)]
