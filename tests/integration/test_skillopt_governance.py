"""SkillOpt governance: contamination + negative-transfer gates (Alpha 15 WS F/G)."""

from __future__ import annotations

from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_dataset import build_skill_dataset
from acp.training.skill_edit import SkillEdit, apply_edits, edits_within_bound
from acp.training.skillopt_backend import ACPInternalSkillOptBackend, optimize_skill


def _ok(i):
    return {"task": f"t{i}", "task_type": "bugfix", "adapter": "openai_harness",
            "is_harness": True, "success": True, "status": "succeeded", "tool_calls": 2,
            "commands": 1, "file_reads": 1}


def _infra(i):
    return {"task": f"x{i}", "task_type": "bugfix", "adapter": "openai_harness",
            "is_harness": True, "success": False, "status": "timed_out",
            "timed_out": True, "tool_calls": 0, "error": "timed out"}


def _provider(i):
    return {"task": f"p{i}", "task_type": "bugfix", "adapter": "openai_harness",
            "is_harness": True, "success": False, "status": "failed",
            "error": "429 rate limit"}


def test_contamination_excluded_from_train_and_heldout() -> None:
    cells = [_ok(i) for i in range(6)] + [_infra(i) for i in range(3)] + [_provider(i)
                                                                          for i in range(2)]
    ds = build_skill_dataset(cells)
    all_ids = {t.task_id for t in ds.train + ds.held_out}
    # No infra/provider task id leaked into the trusted dataset.
    assert not any(tid.startswith(("x", "p")) for tid in all_ids)
    assert ds.excluded_contaminated == 5 and ds.n == 6


def test_negative_transfer_rejected_when_heldout_does_not_improve() -> None:
    # An edit the proposer loves but that does NOT raise held-out score is not deployed.
    base = SkillDocument(name="s", content="# Skill\n", scope=SkillScope())
    ds = build_skill_dataset([_ok(i) for i in range(6)])
    run = optimize_skill(
        base, ds, scorer=lambda c, h: 0.5,  # held-out flat regardless of edits
        proposer=lambda t, c: [SkillEdit("append", content="- looks helpful")],
        backend=ACPInternalSkillOptBackend(), max_steps=3)
    assert not run.deployable and run.best_score == run.base_score
    assert any("not deployable" in n for n in run.notes)


def test_skill_that_regresses_heldout_is_never_best() -> None:
    # A candidate that LOWERS held-out score must be rejected by the gate.
    base = SkillDocument(name="s", content="# good\n", scope=SkillScope())
    ds = build_skill_dataset([_ok(i) for i in range(6)])

    def scorer(content, held):
        return 0.2 if "- harmful" in content else 0.8  # edit lowers the score

    run = optimize_skill(
        base, ds, scorer=scorer,
        proposer=lambda t, c: [SkillEdit("append", content="- harmful")],
        backend=ACPInternalSkillOptBackend(), max_steps=3)
    assert run.best_score == 0.8 and not run.deployable  # baseline retained, edit rejected
    assert run.rejected >= 1


def test_edit_bound_enforced() -> None:
    assert edits_within_bound([SkillEdit("append") for _ in range(8)])
    assert not edits_within_bound([SkillEdit("append") for _ in range(9)])


def test_secrets_never_persist_in_skill() -> None:
    out = apply_edits("# Skill\n", [SkillEdit("append",
                      content="export OPENAI_API_KEY=sk-livesecretvalue123456")])
    assert "sk-livesecretvalue123456" not in out
