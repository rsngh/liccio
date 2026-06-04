"""Skill composition — combine a scoped skill library into one context (Alpha 21 WS7).

A skill-library OS routes not one skill but the *set* applicable to a task. Composition
must be safe and compact: detect conflicts (dedup duplicate/contradictory directives),
order by safety then validated benefit, and respect a token budget (a skill document is
external state the frozen agent reads every step — it cannot grow without bound). The
result records exactly which skills were included/excluded and why, for the dossier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.schemas.skill import SkillDocument

DEFAULT_TOKEN_BUDGET = 1200
_RISK_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class SkillCompositionResult:
    content: str
    included: list[dict] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)  # skill_id -> reason
    token_estimate: int = 0
    conflicts_resolved: int = 0


def _lines(skill: SkillDocument) -> list[str]:
    return [ln for ln in skill.content.splitlines() if ln.strip().startswith("-")]


def _contradicts(a: str, b: str) -> bool:
    """Crude contradiction heuristic: one says 'always/must' a thing the other 'never/
    don't' negates on the same key phrase."""
    al, bl = a.lower(), b.lower()
    pos = any(w in al for w in ("always", "must", "ensure"))
    neg = any(w in bl for w in ("never", "don't", "do not", "avoid"))
    if not (pos and neg):
        return False
    # share a meaningful token (>3 chars) beyond the directive words
    stop = {"always", "must", "ensure", "never", "don't", "avoid", "the", "and",
            "before", "after", "with", "your"}
    at = {w for w in al.split() if len(w) > 3 and w not in stop}
    bt = {w for w in bl.split() if len(w) > 3 and w not in stop}
    return bool(at & bt)


def compose_skills(
    skills: list[SkillDocument], *, token_budget: int = DEFAULT_TOKEN_BUDGET,
    risk_level: str = "medium",
) -> SkillCompositionResult:
    """Compose applicable skills into one ordered, deduped, budgeted document."""
    # Order: safety (risk_class) first, then higher validated benefit, then version.
    ordered = sorted(
        skills, key=lambda s: (_RISK_RANK.get(s.risk_class, 1),
                               -(s.held_out_score or 0.0), -s.version))
    result = SkillCompositionResult(content="")
    kept_lines: list[str] = []
    header = "# Composed skill\n"
    tokens = max(1, len(header) // 4)
    for s in ordered:
        # Conflict detection against already-kept lines.
        s_lines: list[str] = []
        conflict = False
        for ln in _lines(s):
            norm = ln.strip().lower()
            if any(norm == k.strip().lower() for k in kept_lines):
                result.conflicts_resolved += 1  # duplicate -> drop
                continue
            if any(_contradicts(ln, k) or _contradicts(k, ln) for k in kept_lines):
                result.conflicts_resolved += 1
                conflict = True
                continue
            s_lines.append(ln)
        if not s_lines:
            result.excluded[s.id] = "no new non-conflicting directives" if not conflict \
                else "conflicts with a higher-priority skill"
            continue
        add_tokens = sum(max(1, len(ln) // 4) for ln in s_lines)
        if tokens + add_tokens > token_budget:
            result.excluded[s.id] = "exceeds token budget"
            continue
        kept_lines.extend(s_lines)
        tokens += add_tokens
        result.included.append({"skill_id": s.id, "version": s.version,
                                "scope": s.scope.key(), "lines": len(s_lines)})
    result.content = header + "\n".join(kept_lines) + ("\n" if kept_lines else "")
    result.token_estimate = tokens
    return result
