# ruff: noqa: E501
"""SkillBank — offline tests: bounded edits, validation gate, injection, isolation."""

from __future__ import annotations

from acp.memory.skill_bank import SkillBank


def test_bounded_edits_dedupe_and_cap() -> None:
    sb = SkillBank(max_bullets=2)
    assert sb.apply_edit(tenant="t", repo_family="f", op="add", bullet="Preserve lazy iterator semantics.")
    assert not sb.apply_edit(tenant="t", repo_family="f", op="add", bullet="preserve  lazy iterator semantics")  # dup (normalized)
    assert sb.apply_edit(tenant="t", repo_family="f", op="add", bullet="Keep __all__ sorted")
    assert not sb.apply_edit(tenant="t", repo_family="f", op="add", bullet="third")  # cap
    assert sb.apply_edit(tenant="t", repo_family="f", op="replace", index=1, bullet="Update __all__ when adding functions")
    assert sb.apply_edit(tenant="t", repo_family="f", op="delete", index=0)
    assert len(sb.doc(tenant="t", repo_family="f").bullets) == 1


def test_validation_gate_keeps_improving_edit_and_reverts_regression() -> None:
    sb = SkillBank()
    def validate(doc: str) -> float:  # doc containing the good bullet scores higher
        return 0.5 if "edge cases" in doc else 0.3
    assert sb.propose_and_validate(tenant="t", repo_family="f", op="add",
                                   bullet="Handle empty/edge cases explicitly in fixes", validate_fn=validate)
    assert "edge cases" in sb.render(tenant="t", repo_family="f")
    # a regressing bullet is reverted and counted
    def validate_regress(doc: str) -> float:
        return 0.1 if "rewrite everything" in doc else 0.5
    assert not sb.propose_and_validate(tenant="t", repo_family="f", op="add",
                                       bullet="Always rewrite everything from scratch", validate_fn=validate_regress)
    d = sb.doc(tenant="t", repo_family="f")
    assert "rewrite everything" not in sb.render(tenant="t", repo_family="f")
    assert d.accepted_edits == 1 and d.rejected_edits == 1


def test_render_empty_and_tenant_family_isolation() -> None:
    sb = SkillBank()
    assert sb.render(tenant="t", repo_family="f") == ""
    sb.apply_edit(tenant="t", repo_family="f", op="add", bullet="A lesson")
    assert sb.render(tenant="other", repo_family="f") == ""   # tenant isolation
    assert sb.render(tenant="t", repo_family="g") == ""       # family isolation
    assert "FAMILY PLAYBOOK (f)" in sb.render(tenant="t", repo_family="f")
