"""SkillOpt provenance graph — full traceability (Alpha 21 WS3)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_edit import SkillEdit
from acp.training.skill_loop import optimize_and_deploy
from acp.training.skill_provenance import trace_skill
from acp.training.skillopt_backend import ACPInternalSkillOptBackend


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'prov.db'}")
    create_all(e)
    return make_session_factory(e)


def _cells():
    return [{"task": f"t{i}", "task_type": "bugfix", "adapter": "openai_harness",
             "is_harness": True, "success": True, "status": "succeeded", "tool_calls": 2,
             "commands": 1, "file_reads": 1} for i in range(8)]


def _scorer(content, held):
    return 1.0 if "- verify" in content else 0.4


def _proposer(train, current):
    return [] if "- verify" in current else [SkillEdit("append", content="- verify")]


def test_every_skill_line_is_traceable(tmp_path) -> None:
    sf = _sf(tmp_path)
    base = SkillDocument(name="bugfix", content="# Skill\n",
                         scope=SkillScope(task_type="bugfix", harness="openai_harness"),
                         provenance=["eval_run_42"])
    with session_scope(sf) as s:
        optimize_and_deploy(EntityStore(s), base, _cells(), scorer=_scorer,
                            proposer=_proposer, backend=ACPInternalSkillOptBackend(),
                            max_steps=3)
    with session_scope(sf) as s:
        runs = trace_skill(EntityStore(s), scope_key=base.scope.key())
    assert len(runs) == 1
    prov = runs[0]
    # Traceable to rollout evidence + a candidate with edit + validation + gate decision.
    assert prov.evidence_run_ids == ["eval_run_42"]
    assert prov.deployed and prov.deployed_skill_id
    accepted = [c for c in prov.candidates if c.gate_action == "accept_new_best"]
    assert accepted, "expected an accepted candidate in the provenance"
    cand = accepted[0]
    assert cand.validation_score == 1.0
    assert any(e.content == "- verify" for e in cand.edits)


def test_provenance_redacts_secret_edits(tmp_path) -> None:
    sf = _sf(tmp_path)
    base = SkillDocument(name="s", content="# Skill\n", scope=SkillScope(task_type="docs"))
    with session_scope(sf) as s:
        optimize_and_deploy(
            EntityStore(s), base, _cells(), scorer=lambda c, h: 0.5,
            proposer=lambda t, c: [SkillEdit("append",
                                   content="token=sk-provenancesecret123456")],
            backend=ACPInternalSkillOptBackend(), max_steps=2)
    with session_scope(sf) as s:
        runs = trace_skill(EntityStore(s), scope_key=base.scope.key())
    blob = runs[0].model_dump_json()
    assert "sk-provenancesecret123456" not in blob
