# ruff: noqa: E501
"""P12 W4: repo-level referee pure helpers — diff parsing, module discovery, decision core (no I/O)."""

from __future__ import annotations

from evals.issue_replay.swebench_referee import (
    _changed_modules,
    _is_test_path,
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


def test_decide_truth_table() -> None:
    # regression failure dominates everything
    ok, _ = decide(regression_ok=False, repro_admissible=True, repro_pass=True, debate_accept=True)
    assert not ok
    # admissible repro that still fails -> reject
    ok, _ = decide(regression_ok=True, repro_admissible=True, repro_pass=False, debate_accept=True)
    assert not ok
    # all three clauses satisfied -> accept
    ok, why = decide(regression_ok=True, repro_admissible=True, repro_pass=True, debate_accept=True)
    assert ok and "repro-pass" in why
    # no admissible repro -> decision rests on guard + debate
    ok, why = decide(regression_ok=True, repro_admissible=False, repro_pass=False, debate_accept=True)
    assert ok and "no-admissible-repro" in why
    ok, _ = decide(regression_ok=True, repro_admissible=False, repro_pass=False, debate_accept=False)
    assert not ok                                # debate veto with no repro
