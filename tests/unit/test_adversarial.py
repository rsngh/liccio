"""Adversarial verification detectors (round-1 goal §6)."""

from __future__ import annotations

from acp.schemas.workspace import DiffBundle
from acp.verification.adversarial import has_high_severity, scan_diff, severity_score


def _diff(text: str, changed=None, deleted=None) -> DiffBundle:
    return DiffBundle(unified_diff=text, changed_files=changed or [], deleted_files=deleted or [])


def test_deleted_test_file_high() -> None:
    f = scan_diff(_diff("", deleted=["tests/test_core.py"]))
    assert any(x.code == "deleted_test" and x.severity == "high" for x in f)


def test_weakened_assertions() -> None:
    text = "--- a/t.py\n+++ b/t.py\n-    assert x == 1\n-    assert y == 2\n+    pass\n"
    f = scan_diff(_diff(text))
    assert any(x.code == "weakened_assertions" for x in f)


def test_removed_test_function() -> None:
    text = "-def test_foo():\n-    assert True\n"
    f = scan_diff(_diff(text))
    assert any(x.code == "removed_test_fn" for x in f)


def test_added_skip() -> None:
    text = "+    pytest.skip('flaky')\n"
    f = scan_diff(_diff(text))
    assert any(x.code == "added_skip" for x in f)


def test_broad_except() -> None:
    text = "+    try:\n+        run()\n+    except Exception:\n+        pass\n"
    f = scan_diff(_diff(text))
    assert any(x.code == "broad_except" for x in f)


def test_security_sensitive_file() -> None:
    f = scan_diff(_diff("", changed=["src/auth/login.py"]))
    assert any(x.code == "security_sensitive_file" for x in f)


def test_unrelated_churn() -> None:
    changed = [f"mod{i}.py" for i in range(8)]
    f = scan_diff(_diff("", changed=changed), expected_paths={"mod0.py"})
    assert any(x.code == "unrelated_churn" for x in f)


def test_clean_diff_no_findings() -> None:
    text = "--- a/m.py\n+++ b/m.py\n+    return a / b\n+    assert divide(6, 2) == 3\n"
    f = scan_diff(_diff(text, changed=["m.py"]))
    assert not has_high_severity(f)
    assert severity_score(f) == 0.0
