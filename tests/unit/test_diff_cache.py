# ruff: noqa: E501
"""DiffCache — offline tests with a real temp git repo: trust-gate, recall, git-apply, drift, isolation."""

from __future__ import annotations

import subprocess

import pytest

from acp.memory.diff_cache import DiffCache


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.com")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")
    (r / "m.py").write_text("def add(a, b):\n    return a - b\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _diff_fixing_add(repo) -> str:
    (repo / "m.py").write_text("def add(a, b):\n    return a + b\n")
    d = subprocess.run(["git", "-C", str(repo), "diff"], capture_output=True, text=True, check=True).stdout
    _git(repo, "checkout", "--", "m.py")  # revert so the workspace is "buggy" again
    return d


def test_record_trust_gated_recall_and_replay_applies(repo) -> None:
    diff = _diff_fixing_add(repo)
    dc = DiffCache()
    assert dc.record(repo_id="R", failure_signature="AssertionError:add", unified_diff=diff, verified=False) is False  # unverified rejected
    assert dc.record(repo_id="R", failure_signature="AssertionError:add", unified_diff=diff, verified=True) is True
    assert dc.replay(tenant="tenant_a", repo_id="R", failure_signature="AssertionError:add", workspace=repo) is True
    assert "return a + b" in (repo / "m.py").read_text()   # cached fix now in the workspace


def test_recall_misses_and_tenant_isolation(repo) -> None:
    dc = DiffCache()
    dc.record(repo_id="R", failure_signature="sig", unified_diff=_diff_fixing_add(repo), verified=True)
    assert dc.replay(tenant="tenant_a", repo_id="R", failure_signature="other", workspace=repo) is False  # wrong sig
    assert dc.replay(tenant="other", repo_id="R", failure_signature="sig", workspace=repo) is False        # wrong tenant
    assert "return a - b" in (repo / "m.py").read_text()   # workspace untouched on a miss


def test_drifted_patch_does_not_apply(repo) -> None:
    dc = DiffCache()
    dc.record(repo_id="R", failure_signature="sig", unified_diff=_diff_fixing_add(repo), verified=True)
    # the module drifted so the cached diff's context no longer matches -> apply must fail cleanly
    (repo / "m.py").write_text("def add(x, y):\n    return x - y  # renamed params\n")
    assert dc.replay(tenant="tenant_a", repo_id="R", failure_signature="sig", workspace=repo) is False
    assert "renamed params" in (repo / "m.py").read_text()  # left as-is, no partial apply
