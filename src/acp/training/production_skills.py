"""A first production-grade skill suite (Alpha 21 WS6).

Curated, inspectable, scoped starter skills — each a compact procedural document with a
risk class and scope. They seed the library so routing has real skills to compose from
day one; each is poison-scan-clean and ready for canary validation before going ACTIVE.
"""

from __future__ import annotations

from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_registry import save_skill

# (name, content, scope kwargs, risk_class)
_SUITE: list[tuple[str, str, dict, str]] = [
    ("bugfix_pytest",
     "# bugfix\n- Reproduce the bug, then make the minimal fix.\n"
     "- After editing, run the project's tests and iterate until they pass.\n",
     {"task_type": "bugfix"}, "low"),
    ("minimal_diff",
     "# minimal diff\n- Change as few lines as possible to satisfy the task.\n"
     "- Do not reformat or touch unrelated code.\n",
     {}, "low"),
    ("security_strict_verifier",
     "# security\n- Always run the strict verifier; never weaken or skip it.\n"
     "- Prefer a safe API over eval/exec and validate all inputs.\n",
     {"task_type": "security_fix", "risk_level": "high"}, "high"),
    ("ci_triage",
     "# ci triage\n- Read the failing test output before editing.\n"
     "- Fix the root cause, then re-run the failing test to confirm green.\n",
     {"task_type": "ci_fix"}, "low"),
    ("test_generation_verify",
     "# test generation\n- Compute expected values by running the code, not by guessing.\n"
     "- Run the generated tests and confirm they pass before finishing.\n",
     {"task_type": "test_generation"}, "low"),
]


def production_skill_suite() -> list[SkillDocument]:
    """The curated starter skills (status CANDIDATE — validate before activating)."""
    return [SkillDocument(name=name, content=content,
                          scope=SkillScope(**scope), risk_class=risk,
                          status=SkillStatus.CANDIDATE, rationale="production starter suite")
            for name, content, scope, risk in _SUITE]


def seed_production_skills(store: EntityStore) -> int:
    """Persist the starter suite (as CANDIDATE). Returns the count seeded."""
    skills = production_skill_suite()
    for s in skills:
        save_skill(store, s)
    return len(skills)
