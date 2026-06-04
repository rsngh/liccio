"""Microsoft SkillOpt backend hardening (Alpha 21 WS4).

Robust adapters for the real ``skillopt`` package: translate an ACP optimization request
into a ``skillopt.BatchSpec``, import a SkillOpt ``best_skill`` artifact into a governed
(poison-scanned) SkillDocument, and report backend status with precise diagnostics — so
`acp skill optimize --backend microsoft_skillopt` either runs or skips actionably.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acp.core.enums import SkillStatus
from acp.core.optional import try_import
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_dataset import SkillDataset
from acp.training.skill_poisoning import scan_skill


class SkillOptConfigTranslator:
    """Translate an ACP dataset/run config into skillopt batch specs."""

    @staticmethod
    def to_batch_spec(dataset: SkillDataset, *, phase: str = "train", seed: int = 0) -> Any:
        """A ``skillopt.BatchSpec`` for the phase (or a plain dict if not installed)."""
        items = dataset.train if phase == "train" else dataset.held_out
        skillopt = try_import("skillopt")
        spec = {"phase": phase, "split": phase, "seed": seed,
                "batch_size": len(items), "payload": [t.task_id for t in items]}
        if skillopt is None:
            return spec
        return skillopt.BatchSpec(**spec)


@dataclass
class ImportedSkill:
    skill: SkillDocument | None
    safe: bool
    findings: list[dict]


def import_best_skill(content: str, *, name: str, scope: SkillScope) -> ImportedSkill:
    """Import a SkillOpt best_skill artifact into a governed SkillDocument.

    The imported skill is poison-scanned before it can become a candidate; a flagged
    artifact yields ``skill=None`` so it can never enter the registry.
    """
    scan = scan_skill(content)
    if not scan.safe:
        return ImportedSkill(skill=None, safe=False, findings=scan.findings)
    skill = SkillDocument(name=name, content=content, scope=scope,
                          status=SkillStatus.CANDIDATE,
                          rationale="imported from skillopt best_skill")
    return ImportedSkill(skill=skill, safe=True, findings=[])


def backend_status() -> dict:
    """Precise diagnostics for the microsoft_skillopt backend."""
    skillopt = try_import("skillopt")
    if skillopt is None:
        return {"available": False, "reason": "skillopt not installed",
                "remedy": "pip install skillopt", "internal_fallback": True}
    return {"available": True, "version": getattr(skillopt, "__version__", "?"),
            "has_evaluate_gate": hasattr(skillopt.evaluation, "evaluate_gate"),
            "internal_fallback": True}
