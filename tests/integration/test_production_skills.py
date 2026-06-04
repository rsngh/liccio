"""Production-grade starter skill suite (Alpha 21 WS6)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.training.production_skills import production_skill_suite, seed_production_skills
from acp.training.skill_poisoning import scan_skill
from acp.training.skill_registry import list_skills


def test_suite_is_scoped_risk_classed_and_poison_clean() -> None:
    suite = production_skill_suite()
    assert len(suite) >= 5
    for s in suite:
        assert s.risk_class in ("low", "medium", "high")
        assert scan_skill(s.content).safe, f"{s.name} flagged by poison scan"
    # The security skill is high-risk and never weakens the verifier.
    sec = next(s for s in suite if s.name == "security_strict_verifier")
    assert sec.risk_class == "high" and "never weaken" in sec.content.lower()


def test_seed_persists_candidates(tmp_path) -> None:
    e = make_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    create_all(e)
    sf = make_session_factory(e)
    with session_scope(sf) as s:
        n = seed_production_skills(EntityStore(s))
    with session_scope(sf) as s:
        got = list_skills(EntityStore(s), status=SkillStatus.CANDIDATE)
    assert n == len(got) >= 5
