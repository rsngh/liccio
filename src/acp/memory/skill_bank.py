# ruff: noqa: E501
"""SkillBank — per-repo-family evolved skill documents (SkillOpt 2605.23904, ACE/GEPA patterns).

The measured moat is longitudinal: SolutionStore pays on EXACT recurrence (same bug twice). SkillBank
generalizes to FAMILY-level learning: distill what past attempts on a repo family taught us
("fixes must preserve lazy-iterator semantics", "tests parametrize exhaustively — handle edge cases")
into a compact playbook injected into any rung's prompt the next time we work that family. Value needs
only the same *codebase* twice, not the same bug — the realistic deployment.

Mechanics (kept text-space + dependency-free; the LLM reflection that PROPOSES bullets lives in the
eval/caller, like repair_v2 does):
  * a skill doc is <=`max_bullets` short imperative bullets per (tenant, repo_family);
  * edits are bounded ops (add/replace/delete one bullet at a time);
  * `propose_and_validate` accepts an edit ONLY if a caller-supplied validation function (e.g. solve
    rate on held-out family bundles) does not regress — the SkillOpt gate that stops prompt rot;
  * `render` produces the injection block, capped, deterministic order.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillDoc:
    bullets: list[str] = field(default_factory=list)
    accepted_edits: int = 0
    rejected_edits: int = 0


def _norm(b: str) -> str:
    return " ".join(b.split()).strip().rstrip(".")


@dataclass
class SkillBank:
    """Tenant-isolated store of per-repo-family skill documents."""

    max_bullets: int = 8
    max_bullet_chars: int = 200
    docs: dict[tuple[str, str], SkillDoc] = field(default_factory=dict)

    def doc(self, *, tenant: str, repo_family: str) -> SkillDoc:
        return self.docs.setdefault((tenant, repo_family), SkillDoc())

    # --- bounded edits -------------------------------------------------------------------
    def apply_edit(self, *, tenant: str, repo_family: str, op: str, bullet: str = "",
                   index: int = -1) -> bool:
        """One bounded edit: add | replace | delete. Returns False if malformed/no-op."""
        d = self.doc(tenant=tenant, repo_family=repo_family)
        b = _norm(bullet)[: self.max_bullet_chars]
        existing = {_norm(x).lower() for x in d.bullets}
        if op == "add":
            if not b or b.lower() in existing or len(d.bullets) >= self.max_bullets:
                return False
            d.bullets.append(b)
            return True
        if op == "replace":
            if not b or not (0 <= index < len(d.bullets)) or b.lower() in existing:
                return False
            d.bullets[index] = b
            return True
        if op == "delete":
            if not (0 <= index < len(d.bullets)):
                return False
            d.bullets.pop(index)
            return True
        return False

    def propose_and_validate(self, *, tenant: str, repo_family: str, op: str, bullet: str = "",
                             index: int = -1, validate_fn) -> bool:
        """SkillOpt gate: apply the edit, score via `validate_fn(rendered_doc) -> float`, and KEEP it
        only if the score does not regress vs the current doc. Reverts on regression."""
        d = self.doc(tenant=tenant, repo_family=repo_family)
        before_bullets = list(d.bullets)
        base = validate_fn(self.render(tenant=tenant, repo_family=repo_family))
        if not self.apply_edit(tenant=tenant, repo_family=repo_family, op=op, bullet=bullet, index=index):
            return False
        after = validate_fn(self.render(tenant=tenant, repo_family=repo_family))
        if after < base:           # strict no-regression gate
            d.bullets = before_bullets
            d.rejected_edits += 1
            return False
        d.accepted_edits += 1
        return True

    # --- injection -----------------------------------------------------------------------
    def render(self, *, tenant: str, repo_family: str) -> str:
        d = self.docs.get((tenant, repo_family))
        if not d or not d.bullets:
            return ""
        lines = "\n".join(f"- {b}" for b in d.bullets[: self.max_bullets])
        return f"FAMILY PLAYBOOK ({repo_family}) — lessons from prior fixes in this codebase:\n{lines}"
