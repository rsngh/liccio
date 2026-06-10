# ruff: noqa: E501
"""Solution store — offline tests: extract, trust-gated record, splice-replay, drift fallback."""

from __future__ import annotations

from acp.memory.solution_store import (
    SolutionStore,
    extract_functions,
    signature_of,
    splice_functions,
)

BUGGY = "def add(a, b):\n    return a - b  # bug\n\n\ndef mul(a, b):\n    return a * b\n"
FIXED = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"


def test_extract_and_splice_roundtrip_fixes_the_buggy_function() -> None:
    funcs = extract_functions(FIXED, ("add",))
    assert funcs and funcs[0][0] == "add"
    spliced = splice_functions(BUGGY, funcs)
    assert "return a + b" in spliced and "return a * b" in spliced  # fixed add, untouched mul
    ns: dict = {}
    exec(spliced, ns)  # noqa: S102 - executing trusted test source
    assert ns["add"](2, 3) == 5


def test_record_is_trust_gated_then_replays() -> None:
    st = SolutionStore()
    assert st.record(repo_family="acme", failure_signature="AssertionError:add", module_path="m.py",
                     fixed_module_src=FIXED, function_names=("add",), verified=False) is False  # unverified rejected
    assert st.record(repo_family="acme", failure_signature="AssertionError:add", module_path="m.py",
                     fixed_module_src=FIXED, function_names=("add",), verified=True) is True
    cand = st.replay(tenant="tenant_a", repo_family="acme", failure_signature="AssertionError:add",
                     buggy_module_src=BUGGY)
    assert cand is not None and "return a + b" in cand


def test_replay_misses_are_none_signature_and_tenant_isolation() -> None:
    st = SolutionStore()
    st.record(repo_family="acme", failure_signature="AssertionError:add", module_path="m.py",
              fixed_module_src=FIXED, function_names=("add",), verified=True)
    # wrong signature, wrong tenant -> no hit (caller falls back to the live ladder)
    assert st.replay(tenant="tenant_a", repo_family="acme", failure_signature="KeyError:other", buggy_module_src=BUGGY) is None
    assert st.replay(tenant="tenant_b", repo_family="acme", failure_signature="AssertionError:add", buggy_module_src=BUGGY) is None
    # drift: the cached function no longer exists in the (rewritten) module -> safe None, no bad splice
    assert splice_functions("def renamed(a, b):\n    return 0\n", (("add", "def add(a,b):\n    return a+b\n"),)) is None


def test_signature_of_extracts_exception_and_symbol() -> None:
    assert signature_of("E   AssertionError: 5 != 6", "add") == "AssertionError:add"
    assert signature_of("E   KeyError: 'x'") == "KeyError"
