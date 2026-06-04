"""Skill-document edit engine (Alpha 15 WS3/WS5).

SkillOpt represents a skill update as a small set of bounded edits (append /
insert_after / replace / delete). The ``skillopt`` library defines the ``Edit`` type
and the validation gate but leaves *applying* an edit to the host; this module is that
mechanic, plus a redaction pass so a learned skill can never carry a secret forward.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.core.redaction import Redactor

# Editorial bound: a single optimization step may not change more than this many
# lines, keeping skills compact and edits reviewable (SkillOpt "bounded edits").
MAX_EDITS_PER_STEP = 8


@dataclass
class SkillEdit:
    """A bounded edit (mirrors skillopt.Edit; usable without the library installed)."""

    op: str  # append | insert_after | replace | delete
    content: str = ""
    target: str = ""


def _from_skillopt(edit: object) -> SkillEdit:
    return SkillEdit(op=getattr(edit, "op", "append"),
                     content=getattr(edit, "content", ""),
                     target=getattr(edit, "target", ""))


def apply_edits(content: str, edits: list) -> str:
    """Apply bounded edits to a markdown skill document, returning new content.

    ``edits`` items may be :class:`SkillEdit` or ``skillopt.Edit`` (duck-typed).
    Unknown ops are ignored (defensive). Secrets are redacted from the result so a
    skill can never persist a leaked credential.
    """
    norm = [e if isinstance(e, SkillEdit) else _from_skillopt(e) for e in edits]
    lines = content.splitlines()
    for e in norm[:MAX_EDITS_PER_STEP]:
        if e.op == "append":
            lines.append(e.content)
        elif e.op == "insert_after":
            out: list[str] = []
            inserted = False
            for ln in lines:
                out.append(ln)
                if not inserted and e.target and e.target in ln:
                    out.append(e.content)
                    inserted = True
            if not inserted:  # target not found -> append
                out.append(e.content)
            lines = out
        elif e.op == "replace":
            lines = [ln.replace(e.target, e.content) if e.target and e.target in ln
                     else ln for ln in lines]
        elif e.op == "delete":
            lines = [ln for ln in lines if not (e.target and e.target in ln)]
    result = "\n".join(lines)
    if content.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return Redactor().redact_text(result)


def edits_within_bound(edits: list) -> bool:
    """True if the edit set respects the per-step bound (reviewable + compact)."""
    return len(edits) <= MAX_EDITS_PER_STEP
