"""SkillOpt edit engine + dataset + governed optimization loop (Alpha 15 WS3/4/5)."""

from __future__ import annotations

from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_dataset import build_skill_dataset
from acp.training.skill_edit import SkillEdit, apply_edits
from acp.training.skillopt_backend import (
    ACPInternalSkillOptBackend,
    MicrosoftSkillOptBackend,
    get_backend,
    next_version,
    optimize_skill,
)


def test_apply_edits_ops() -> None:
    base = "# Skill\n- read first\n"
    out = apply_edits(base, [
        SkillEdit("append", content="- run tests"),
        SkillEdit("insert_after", content="- understand the task", target="# Skill"),
        SkillEdit("replace", content="- always read first", target="- read first"),
    ])
    assert "- run tests" in out and "- understand the task" in out
    assert "- always read first" in out


def test_apply_edits_redacts_secrets() -> None:
    out = apply_edits("# Skill\n", [SkillEdit("append", content="key=sk-ABC123secrettoken")])
    assert "sk-ABC123secrettoken" not in out


def _cells():
    ok = [{"task": f"t{i}", "task_type": "bugfix", "adapter": "openai_harness",
           "is_harness": True, "success": True, "status": "succeeded", "tool_calls": 2,
           "commands": 1, "file_reads": 1} for i in range(8)]
    # contaminated infra rows must be excluded from the dataset
    bad = [{"task": f"x{i}", "task_type": "bugfix", "adapter": "openai_harness",
            "is_harness": True, "success": False, "status": "timed_out", "timed_out": True,
            "tool_calls": 0, "error": "timed out"} for i in range(3)]
    return ok + bad


def test_dataset_excludes_contaminated_and_splits() -> None:
    ds = build_skill_dataset(_cells(), held_out_frac=0.4)
    assert ds.excluded_contaminated == 3
    assert ds.n == 8 and ds.train and ds.held_out


def _scorer_factory():
    # Reward a skill that contains the magic line "- verify with tests".
    def scorer(content, held_out):
        return 1.0 if "- verify with tests" in content else 0.5
    return scorer


def _proposer(train, current):
    if "- verify with tests" in current:
        return []  # nothing more to do
    return [SkillEdit("append", content="- verify with tests")]


def _run(backend):
    base = SkillDocument(name="bugfix", content="# Skill\n- read first\n",
                         scope=SkillScope(task_type="bugfix"))
    ds = build_skill_dataset(_cells())
    return optimize_skill(base, ds, scorer=_scorer_factory(), proposer=_proposer,
                          backend=backend, max_steps=4)


def test_internal_backend_accepts_improving_edit() -> None:
    run = _run(ACPInternalSkillOptBackend())
    assert run.improved and run.deployable
    assert run.best_score == 1.0 and run.accepted >= 1
    assert "- verify with tests" in run.best_content


def test_no_improvement_is_not_deployable() -> None:
    base = SkillDocument(name="s", content="# Skill\n", scope=SkillScope())
    ds = build_skill_dataset(_cells())
    # proposer that only adds a useless line (scorer unaffected) -> no improvement
    run = optimize_skill(base, ds, scorer=lambda c, h: 0.5,
                         proposer=lambda t, c: [SkillEdit("append", content="- noise")],
                         max_steps=3)
    assert not run.deployable and not run.improved


def test_next_version_lineage() -> None:
    backend = ACPInternalSkillOptBackend()
    base = SkillDocument(name="bugfix", content="# Skill\n", scope=SkillScope(task_type="bugfix"))
    ds = build_skill_dataset(_cells())
    run = optimize_skill(base, ds, scorer=_scorer_factory(), proposer=_proposer,
                         backend=backend, max_steps=4)
    nxt = next_version(base, run)
    assert nxt.version == base.version + 1 and nxt.parent_id == base.id
    assert nxt.held_out_score == run.best_score


def test_microsoft_backend_available_and_gates() -> None:
    # skillopt is installed in this environment; the loop runs through its gate.
    b = MicrosoftSkillOptBackend()
    if not b.available():
        import pytest
        pytest.skip("skillopt not installed")
    run = _run(b)
    assert run.backend == "microsoft_skillopt"
    assert run.improved and run.deployable and run.best_score == 1.0


def test_get_backend_falls_back_to_internal() -> None:
    assert get_backend("acp_internal").name == "acp_internal"
    # microsoft resolves to real backend if available, else internal
    assert get_backend("microsoft_skillopt").name in ("microsoft_skillopt", "acp_internal")
