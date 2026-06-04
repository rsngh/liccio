"""Skill registry persistence + diff (Alpha 15 WS2).

Thin governance layer over the EntityStore: persists :class:`SkillDocument` rows with
their ``scope_key`` indexed, queries by scope/status, and produces a human-readable diff
between two versions so a reviewer can audit exactly what an optimization changed.
"""

from __future__ import annotations

import difflib

from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.schemas.skill import SkillDocument


def save_skill(store: EntityStore, skill: SkillDocument) -> SkillDocument:
    """Persist a skill, indexing its scope_key for scoped lookup."""
    store.save(skill, extra_index={"scope_key": skill.scope.key()})
    return skill


def list_skills(store: EntityStore, *, status: SkillStatus | str | None = None,
                scope_key: str | None = None) -> list[SkillDocument]:
    """List skills, optionally filtered by status and/or scope_key."""
    filt: dict = {}
    if status is not None:
        filt["status"] = status.value if isinstance(status, SkillStatus) else status
    if scope_key is not None:
        filt["scope_key"] = scope_key
    return store.list_by(SkillDocument, **filt)


def get_skill(store: EntityStore, skill_id: str) -> SkillDocument | None:
    for s in store.list_by(SkillDocument):
        if s.id == skill_id:
            return s
    return None


def active_skill_for(
    store: EntityStore, *, task_type: str | None = None, risk_level: str | None = None,
    harness: str | None = None, model_family: str | None = None,
) -> SkillDocument | None:
    """The active skill whose scope matches the routing context, if any (the
    highest-version match wins)."""
    matches = [s for s in list_skills(store, status=SkillStatus.ACTIVE)
               if s.scope.matches(task_type=task_type, risk_level=risk_level,
                                  harness=harness, model_family=model_family)]
    return max(matches, key=lambda s: s.version, default=None)


def diff_skills(old: SkillDocument, new: SkillDocument) -> str:
    """Unified diff of two skill documents' content (for `acp skill diff`)."""
    return "\n".join(difflib.unified_diff(
        old.content.splitlines(), new.content.splitlines(),
        fromfile=f"{old.name} v{old.version} ({old.content_sha})",
        tofile=f"{new.name} v{new.version} ({new.content_sha})", lineterm=""))
