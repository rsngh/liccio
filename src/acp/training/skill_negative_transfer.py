"""Skill negative-transfer campaign (Alpha 21 WS10).

A skill optimized for one domain can HURT another (negative transfer). The campaign runs
a skill against in-/near-/out-of-domain task sets, flags domains where the skill is worse
than the no-skill baseline, and automatically narrows the skill's applicability by
recording those domains in ``negative_transfer_history`` — which routing/composition then
excludes. This keeps a broadly-scoped skill from silently degrading the domains it hurts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.schemas.skill import SkillDocument

# A domain must drop by more than this vs baseline to count as negative transfer.
NEG_TRANSFER_EPS = 0.02


@dataclass
class TransferAssessment:
    negative_domains: list[str] = field(default_factory=list)
    positive_domains: list[str] = field(default_factory=list)
    neutral_domains: list[str] = field(default_factory=list)
    deltas: dict[str, float] = field(default_factory=dict)


def assess_transfer(domain_scores: dict[str, tuple[float, float]]) -> TransferAssessment:
    """``domain_scores`` maps a domain (e.g. task_type) -> (baseline, with_skill).

    Classifies each domain as negative / positive / neutral transfer.
    """
    a = TransferAssessment()
    for domain, (base, withskill) in domain_scores.items():
        delta = round(withskill - base, 4)
        a.deltas[domain] = delta
        if delta < -NEG_TRANSFER_EPS:
            a.negative_domains.append(domain)
        elif delta > NEG_TRANSFER_EPS:
            a.positive_domains.append(domain)
        else:
            a.neutral_domains.append(domain)
    return a


def narrow_skill_scope(skill: SkillDocument, negative_domains: list[str]) -> SkillDocument:
    """Return a copy of the skill with the negative-transfer domains recorded, so
    routing/composition will exclude it for those domains (auto-narrowing)."""
    history = sorted(set(skill.negative_transfer_history) | set(negative_domains))
    return skill.model_copy(update={"negative_transfer_history": history})


def applies_to_domain(skill: SkillDocument, domain: str) -> bool:
    """False if the domain is in the skill's negative-transfer history."""
    return domain not in set(skill.negative_transfer_history)
