# ruff: noqa: E501
"""P12 W4: repo-level referee pure helpers — diff parsing, module discovery, decision core (no I/O)."""

from __future__ import annotations

from evals.issue_replay.swebench_referee import (
    _changed_modules,
    _is_test_path,
    _parse_outcomes,
    changed_files,
    decide,
)

_DIFF = (
    "diff --git a/src/pkg/util.py b/src/pkg/util.py\n"
    "--- a/src/pkg/util.py\n"
    "+++ b/src/pkg/util.py\n"
    "@@ -1,3 +1,3 @@\n"
    "-    return a - b\n"
    "+    return a + b\n"
    "diff --git a/tests/test_util.py b/tests/test_util.py\n"
    "--- a/tests/test_util.py\n"
    "+++ b/tests/test_util.py\n"
    "@@ -1,1 +1,2 @@\n"
    "+def test_new(): pass\n"
)


def test_changed_files_excludes_tests() -> None:
    cf = changed_files(_DIFF)
    assert cf == ["src/pkg/util.py"]            # the test file is dropped (fairness)


def test_changed_modules_includes_stem_and_package() -> None:
    mods = _changed_modules(["src/pkg/util.py", "pkg/__init__.py"])
    assert "util" in mods and "pkg" in mods     # both the file stem and its package dir
    assert "src" not in mods and "__init__" not in mods


def test_is_test_path() -> None:
    assert _is_test_path("tests/test_x.py") and _is_test_path("a/test_y.py")
    assert _is_test_path("pkg/x_test.py")
    assert not _is_test_path("src/pkg/util.py")


def test_parse_outcomes_handles_parametrized_ids_with_spaces() -> None:
    # parametrized node ids contain spaces/brackets; the old \S+::\S+ truncated them -> invisible tests
    text = (
        "testing/test_x.py::test_plain PASSED                                  [ 10%]\n"
        "testing/test_x.py::test_get_exprs[assert a == b] FAILED               [ 20%]\n"
        "testing/test_x.py::test_get_exprs[assert foo in bar] PASSED           [ 30%]\n"
    )
    out = _parse_outcomes(text)
    assert out == {
        "testing/test_x.py::test_plain": "PASSED",
        "testing/test_x.py::test_get_exprs[assert a == b]": "FAILED",
        "testing/test_x.py::test_get_exprs[assert foo in bar]": "PASSED",
    }


def test_parse_outcomes_verb_first_fallback() -> None:
    assert _parse_outcomes("PASSED testing/t.py::test_a[x y]\nFAILED testing/t.py::test_b") == {
        "testing/t.py::test_a[x y]": "PASSED", "testing/t.py::test_b": "FAILED"}


def test_decide_truth_table() -> None:
    # accept iff regression_ok AND (repro_pass when admissible, else debate_accept)
    # regression failure is the hard fail-closed gate -> dominates everything
    ok, _ = decide(regression_ok=False, repro_admissible=True, repro_pass=True, debate_accept=True)
    assert not ok
    # repro admissible -> it is REQUIRED: a passing repro commits regardless of debate
    ok, why = decide(regression_ok=True, repro_admissible=True, repro_pass=True, debate_accept=False)
    assert ok and "repro" in why
    # repro admissible but FAILS -> reject even if debate accepts (debate alone commits P2P-breakers)
    ok, _ = decide(regression_ok=True, repro_admissible=True, repro_pass=False, debate_accept=True)
    assert not ok
    # no admissible repro -> fall back to debate
    ok, why = decide(regression_ok=True, repro_admissible=False, repro_pass=False, debate_accept=True)
    assert ok and "debate-accept" in why
    ok, _ = decide(regression_ok=True, repro_admissible=False, repro_pass=False, debate_accept=False)
    assert not ok
