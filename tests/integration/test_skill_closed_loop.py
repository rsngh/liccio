"""End-to-end closed-loop skill optimization + deployment + injection (Round 16)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_edit import SkillEdit
from acp.training.skill_inject import inject_active_skill
from acp.training.skill_loop import optimize_and_deploy
from acp.training.skillopt_backend import ACPInternalSkillOptBackend


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'loop.db'}")
    create_all(e)
    return make_session_factory(e)


def _cells():
    ok = [{"task": f"t{i}", "task_type": "bugfix", "adapter": "openai_harness",
           "is_harness": True, "success": True, "status": "succeeded", "tool_calls": 2,
           "commands": 1, "file_reads": 1} for i in range(8)]
    bad = [{"task": f"x{i}", "task_type": "bugfix", "adapter": "openai_harness",
            "is_harness": True, "success": False, "status": "timed_out", "timed_out": True,
            "tool_calls": 0, "error": "timed out"} for i in range(3)]
    return ok + bad


def _scorer(content, held):
    return 1.0 if "- verify with tests" in content else 0.4


def _proposer(train, current):
    return [] if "- verify with tests" in current else \
        [SkillEdit("append", content="- verify with tests")]


def test_optimize_deploy_inject_end_to_end(tmp_path) -> None:
    sf = _sf(tmp_path)
    base = SkillDocument(name="bugfix", content="# Skill\n", status=SkillStatus.CANDIDATE,
                         scope=SkillScope(task_type="bugfix", harness="openai_harness"))
    with session_scope(sf) as s:
        res = optimize_and_deploy(EntityStore(s), base, _cells(), scorer=_scorer,
                                  proposer=_proposer, backend=ACPInternalSkillOptBackend(),
                                  max_steps=3)
    # The contaminated infra rows were excluded; the loop improved + deployed.
    assert res.excluded_contaminated == 3
    assert res.deployable and res.deployed and res.new_version == 2
    # The deployed skill is now ACTIVE and injected into a matching context.
    with session_scope(sf) as s:
        pack = ContextPack(repo_id="r", task_id="t", snapshot_id="s",
                           items=[ContextItem(kind="file_chunk", path="a.py", content="x")])
        injected, skill = inject_active_skill(EntityStore(s), pack, task_type="bugfix",
                                              harness="openai_harness")
    assert skill is not None and skill.version == 2
    assert "- verify with tests" in injected.items[0].content


def test_loop_does_not_deploy_without_improvement(tmp_path) -> None:
    sf = _sf(tmp_path)
    base = SkillDocument(name="s", content="# Skill\n", scope=SkillScope(task_type="bugfix"))
    with session_scope(sf) as s:
        res = optimize_and_deploy(
            EntityStore(s), base, _cells(), scorer=lambda c, h: 0.4,
            proposer=lambda t, c: [SkillEdit("append", content="- noise")],
            backend=ACPInternalSkillOptBackend(), max_steps=2)
    assert not res.deployable and not res.deployed
