"""No-op / abstention contract (evaluation report P5).

When the agent makes NO change to an already-correct repo, the control plane must not report a
false "succeeded" (a fabricated fix) and must not invent a spurious changed file. It escalates
to human review instead. A positive control (a real fix on a buggy repo -> succeeded) proves
the loop CAN reach success, so the no-op assertion is meaningful rather than vacuous.

Fully deterministic — uses the patch adapter, no API keys.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.api.service import AppService
from acp.core.config import ACPSettings

DIVIDE = next(t for t in BENCH_TASKS if t.name == "divide")


def _make_repo(root: Path, module_src: str) -> Path:
    repo = root / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / DIVIDE.module_path).write_text(module_src)
    (repo / "tests" / f"test_{DIVIDE.name}.py").write_text(DIVIDE.test_src)
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (repo / "pyproject.toml").write_text(  # so the verifier detects + runs pytest
        '[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
        "[tool.pytest.ini_options]\naddopts = \"-q\"\n")
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"],
                 ["git", "config", "commit.gpgsign", "false"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "init"]):
        subprocess.run(argv, cwd=repo, check=False, capture_output=True)
    return repo


def _service(root: Path) -> AppService:
    s = ACPSettings(database_url=f"sqlite+aiosqlite:///{root / 'acp.db'}",
                    artifact_dir=str(root / "art"), workspace_dir=str(root / "ws"))
    return AppService(settings=s)


_TITLE = "Fix divide() to divide instead of add"
_BODY = "divide(a, b) currently returns a + b; it must return a / b so the tests pass."


def _run(root: Path, module_src: str, files: dict[str, str]):
    repo_path = _make_repo(root, module_src)
    svc = _service(root)
    repo = svc.create_repo("c", str(repo_path), default_branch="master")
    # Identical task framing for both scenarios so the ONLY difference is no-op vs real change.
    task = svc.create_task(repo.id, title=_TITLE, body=_BODY,
                           acceptance_criteria=["divide(6, 2) == 3"], metadata={"files": files})
    state = svc.run_task(task.id)
    status = state.status if isinstance(state.status, str) else state.status.value
    diffs = svc.run_diff(state.run_id)
    changed = diffs[0]["changed_files"] if diffs else []
    return status, changed


def test_noop_on_correct_repo_is_not_a_false_success(tmp_path) -> None:
    # already-correct module; the agent writes identical content -> empty diff (a no-op).
    status, changed = _run(tmp_path, DIVIDE.fixed, {DIVIDE.module_path: DIVIDE.fixed})
    assert changed == [], f"no-op must not report changed files, got {changed}"
    assert status != "succeeded", "a no-op must NOT be reported as a successful fix"
    # the safe terminal state is human review / abstention, never an autonomous success
    assert status in ("waiting_for_human", "needs_review", "human_review", "abstained",
                      "failed"), status


def test_real_fix_on_buggy_repo_succeeds(tmp_path) -> None:
    # positive control: a genuine change on a buggy repo CAN reach success -> the no-op
    # assertion above is meaningful, not vacuous.
    status, changed = _run(tmp_path, DIVIDE.buggy, {DIVIDE.module_path: DIVIDE.fixed})
    assert changed == [DIVIDE.module_path], changed
    assert status == "succeeded", status
