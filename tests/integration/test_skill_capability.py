"""Skill capability matrix — which skill works for this task/harness (Alpha 21 WS9)."""

from __future__ import annotations

from acp.training.skill_capability import best_skill_for, build_skill_capability


def _cell(skill_id, success, **kw):
    base = {"skill_id": skill_id, "skill_family": skill_id, "task_type": "bugfix",
            "adapter": "openai_harness", "is_harness": True, "success": success,
            "status": "succeeded" if success else "failed", "tool_calls": 2,
            "commands": 1, "file_reads": 1, "cost_usd": 0.001}
    base.update(kw)
    return base


def test_build_aggregates_per_skill() -> None:
    cells = [_cell("skill_a", True) for _ in range(4)] + [_cell("skill_b", i < 1)
                                                          for i in range(4)]
    caps = build_skill_capability(cells)
    by_id = {c.skill_id: c for c in caps}
    assert by_id["skill_a"].success_rate == 1.0 and by_id["skill_a"].n == 4
    assert by_id["skill_b"].success_rate == 0.25
    assert by_id["skill_a"].har == 1.0 and by_id["skill_a"].hfr == 1.0


def test_excludes_untagged_and_infra_cells() -> None:
    cells = [_cell("skill_a", True) for _ in range(3)]
    cells.append({"task_type": "bugfix", "adapter": "openai_harness", "success": True,
                  "status": "succeeded", "tool_calls": 2})  # no skill_id
    cells.append(_cell("skill_a", False, status="timed_out", timed_out=True,
                       tool_calls=0, error="timed out"))     # infra -> excluded
    caps = build_skill_capability(cells)
    assert len(caps) == 1 and caps[0].n == 3  # only the 3 conclusive tagged cells


def test_best_skill_for_picks_highest_success_then_cost() -> None:
    cells = ([_cell("cheap_good", True, cost_usd=0.001) for _ in range(4)]
             + [_cell("pricey_good", True, cost_usd=0.02) for _ in range(4)]
             + [_cell("bad", False) for _ in range(4)])
    caps = build_skill_capability(cells)
    best = best_skill_for(caps, "bugfix", "openai_harness")
    assert best.skill_id == "cheap_good"


def test_skill_capability_table_spans_vendor_harnesses() -> None:
    # WS17: the matrix answers "which skill works best with Codex CLI on bugfix?".
    from acp.training.skill_capability import skill_capability_table
    cells = (
        [_cell("verify", True, adapter="codex_cli", skill_family="verify") for _ in range(4)]
        + [_cell("noop", i < 1, adapter="codex_cli", skill_family="noop") for i in range(4)]
        + [_cell("verify", True, adapter="claude_code", skill_family="verify")
           for _ in range(4)])
    table = skill_capability_table(cells)
    assert table["codex_cli"]["bugfix"]["skill_id"] == "verify"  # best on codex
    assert table["codex_cli"]["bugfix"]["success_rate"] == 1.0
    assert "claude_code" in table  # vendor harness present in the matrix
