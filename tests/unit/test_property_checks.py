"""P8 W1: property generation hardening + the discriminating-admission gate (Hypothesis, no LLM)."""

from __future__ import annotations

import ast
from pathlib import Path

from acp.verification.property_checks import (
    admit_discriminating,
    harden_property,
    vet_properties,
)
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
    # Hypothesis must FIND the input breaking commutativity on buggy code (proven discriminating)
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


class _FakeMsg:
    def __init__(self, text: str) -> None:
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()


class _FakeClient:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.messages = self
    def create(self, **_kw):
        return _FakeMsg(self._reply)


class _Spec:
    issue_text = "f should be commutative"
    public_test = ""


def test_vet_properties_drops_flagged_overspecified() -> None:
    props = [("pbt", _COMMUTE), ("pbt", _HOLDS)]
    kept, dropped, _cost = vet_properties(_Spec(), props, client=_FakeClient("[1]"))
    assert dropped == 1 and len(kept) == 1 and kept[0][1] == _COMMUTE  # drops index 1 only


def test_vet_properties_never_drops_whole_set_and_failopen() -> None:
    props = [("pbt", _COMMUTE), ("pbt", _HOLDS)]
    # the model flags BOTH -> guard against wiping the discriminating set entirely
    kept, dropped, _ = vet_properties(_Spec(), props, client=_FakeClient("[0, 1]"))
    assert dropped == 0 and kept == props
    # no client -> fail-open (no-op), preserving the example-only behaviour
    kept2, dropped2, cost2 = vet_properties(_Spec(), props, client=None)
    assert kept2 == props and dropped2 == 0 and cost2 == 0.0
