"""Reflexion-style repair — offline tests (pure functions)."""

from __future__ import annotations

from acp.routing.reflective_repair import (
    build_repair_prompt,
    failure_summary,
    should_repair,
)


def test_failure_summary_keeps_assertions_and_bounds() -> None:
    out = "collected 1 item\n" + "noise\n" * 50 + "E       assert f(1)==2\nE       AssertionError: 1 != 2"
    s = failure_summary(out, max_lines=4)
    assert "AssertionError" in s and "assert f(1)==2" in s
    assert s.count("\n") <= 3            # bounded


def test_repair_prompt_includes_failure_and_requests_json() -> None:
    p = build_repair_prompt(issue_text="reverse the string", module_path="r.py",
                            prior_code="def rev(s): return s", failure="assert rev('ab')=='ba'")
    assert "reverse the string" in p and "def rev(s): return s" in p
    assert "assert rev('ab')=='ba'" in p
    assert '"files"' in p and "r.py" in p


def test_should_repair_only_when_all_failed_and_budget_remains() -> None:
    assert should_repair(all_failed=True, depth=0, max_depth=1, spent=0.0, budget=0.1)
    assert not should_repair(all_failed=False, depth=0, max_depth=1, spent=0.0, budget=0.1)
    assert not should_repair(all_failed=True, depth=1, max_depth=1, spent=0.0, budget=0.1)   # depth exhausted
    assert not should_repair(all_failed=True, depth=0, max_depth=1, spent=0.2, budget=0.1)   # budget exhausted
