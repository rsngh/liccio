"""P8 W1: property generation hardening + the discriminating-admission gate (Hypothesis, no LLM)."""

from __future__ import annotations

import ast
from pathlib import Path

from acp.verification.property_checks import admit_discriminating, harden_property
from acp.verification.repair_battery import _run_check_kinds

_BUGGY = "def add(a, b):\n    return a - b\n"      # commutativity-violating bug
_GOLD = "def add(a, b):\n    return a + b\n"
_COMMUTE = (
    "from hypothesis import given, strategies as st\n"
    "import m\n"
    "@given(st.integers(), st.integers())\n"
    "def test_commute(a, b):\n"
    "    assert m.add(a, b) == m.add(b, a)\n"
)
_HOLDS = (   # add(a,0)==a is true even on the buggy a-b -> a guard, not discriminating
    "from hypothesis import given, strategies as st\n"
    "import m\n"
    "@given(st.integers())\n"
    "def test_identity(a):\n"
    "    assert m.add(a, 0) == a\n"
)


def test_harden_injects_bounded_profile_after_imports() -> None:
    h = harden_property(_COMMUTE)
    assert "load_profile('acp_pbt')" in h and "max_examples=60" in h
    tree = ast.parse(h)                      # still valid python
    # profile registration sits after the import block, before the test def
    names = [type(n).__name__ for n in tree.body]
    assert names.index("FunctionDef") > names.index("Expr")  # given decorator def is last


def test_admit_discriminating_via_input_search(tmp_path: Path) -> None:
    # Hypothesis must FIND the input breaking commutativity on the buggy code (proven discriminating)
    disc, guard = admit_discriminating([_COMMUTE], baseline_src=_BUGGY, module_path="m.py",
                                       extra_files={}, root=tmp_path)
    assert len(disc) == 1 and len(guard) == 0
    # the GOLD fix must satisfy it (a valid discriminating signal, not an over-strict check)
    kinds = _run_check_kinds(_GOLD, disc, module_path="m.py", extra_files={},
                             root=tmp_path / "g", tag="g")
    assert kinds == ["pass"]


def test_property_holding_on_buggy_is_guard_not_discriminating(tmp_path: Path) -> None:
    disc, guard = admit_discriminating([_HOLDS], baseline_src=_BUGGY, module_path="m.py",
                                       extra_files={}, root=tmp_path)
    assert len(disc) == 0 and len(guard) == 1   # never falsely admitted
