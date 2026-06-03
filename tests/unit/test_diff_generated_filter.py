"""Generated/build artifacts are excluded from diffs (Alpha 13 live-tuning).

Observed live: codex_cli runs the tests, producing __pycache__/*.pyc, which then
polluted the agent's changed_files / diff metrics. The diff capturer must ignore
generated artifacts so trace quality + the minimality axis reflect real source.
"""

from __future__ import annotations

from git import Repo

from acp.workspaces.diff import DiffCapturer, is_generated


def _repo(tmp_path):
    (tmp_path / "calc.py").write_text("def f():\n    return 1\n")
    r = Repo.init(tmp_path)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calc.py"])
    r.index.commit("init")
    return r


def test_is_generated_matches_artifacts() -> None:
    assert is_generated("__pycache__/calc.cpython-312.pyc")
    assert is_generated("pkg/__pycache__/x.pyc")
    assert is_generated("build/lib/x.py")
    assert is_generated(".pytest_cache/v/cache/lastfailed")
    assert not is_generated("calc.py")
    assert not is_generated("src/module.py")


def test_changed_files_excludes_pycache(tmp_path) -> None:
    base = _repo(tmp_path).head.commit.hexsha
    # Agent edits a real source file ...
    (tmp_path / "calc.py").write_text("def f():\n    return 2\n")
    # ... and running it leaves generated artifacts.
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "calc.cpython-312.pyc").write_bytes(b"\x00\x01generated")
    cap = DiffCapturer(str(tmp_path), base)
    changed = cap.get_changed_files()
    assert "calc.py" in changed
    assert all("__pycache__" not in p and not p.endswith(".pyc") for p in changed)
    # The bundle's changed_files is likewise clean.
    bundle = cap.build_bundle()
    assert all("__pycache__" not in p for p in bundle.changed_files)
