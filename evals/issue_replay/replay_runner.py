"""Issue-replay runner + patch-equivalence judge (GOALS Alpha 44 P1).

Builds each frozen bundle as a repo (buggy + PUBLIC test only; the gold patch and hidden tests
are withheld), optionally runs a policy to produce a fix, then judges by hidden tests AND a
semantic patch-equivalence check (does the produced module behave like the gold patch on probe
inputs?). Offline-fair by construction: buggy fails hidden, gold passes public + hidden.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from evals.issue_replay.replay_task import IssueReplayTask


def _run_test(repo: Path, test_name: str, *, timeout: int = 150) -> bool:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", test_name]
    try:
        return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=timeout,
                              check=False, env=env).returncode == 0
    except subprocess.TimeoutExpired:
        # a hanging/too-slow candidate (e.g. an agent fix with an infinite loop) grades as a FAIL,
        # never crashing the run (more-itertools' large test files can be slow under load)
        return False


def build_repo(task: IssueReplayTask, root: Path, *, module_src: str) -> Path:
    repo = root / task.module_path.replace("/", "_").replace(".py", "")
    repo.mkdir(parents=True, exist_ok=True)
    (repo / task.module_path).parent.mkdir(parents=True, exist_ok=True)  # nested (package) path
    (repo / task.module_path).write_text(module_src)
    for p, c in task.extra_files.items():
        (repo / p).parent.mkdir(parents=True, exist_ok=True)
        (repo / p).write_text(c)
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (repo / "test_public.py").write_text(task.public_test)
    return repo


def verify(task: IssueReplayTask, root: Path, *, module_src: str) -> tuple[bool, bool]:
    """Return (hidden_pass, public_pass) for a candidate module source."""
    repo = build_repo(task, root / f"ver_{id(module_src)}", module_src=module_src)
    (repo / "test_hidden.py").write_text(task.hidden_test)
    return _run_test(repo, "test_hidden.py"), _run_test(repo, "test_public.py")


def patch_equivalent(task: IssueReplayTask, produced_src: str, *, probes: list[str]) -> bool:
    """Semantic equivalence: produced and gold modules return the same values on probe calls."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)

        def outputs(src: str) -> list | None:
            repo = build_repo(task, root / f"eq_{id(src)}", module_src=src)
            mod = task.module_path[:-3].replace("/", ".")  # package bundles import dotted
            ev = "eval(c, {'m': m, '__builtins__': __builtins__})"
            script = ("import json\nimport " + mod + " as m\n"
                      "print(json.dumps([repr(" + ev + ") for c in " + repr(probes) + "]))")
            (repo / "_probe.py").write_text(script)
            r = subprocess.run(["python", "_probe.py"], cwd=repo, capture_output=True, text=True,
                               timeout=30, check=False)
            if r.returncode != 0:
                return None
            import json
            return json.loads(r.stdout)
        return outputs(produced_src) == outputs(task.gold_patch) is not None


def offline_fairness(task: IssueReplayTask, root: Path) -> dict:
    """A bundle is fair iff buggy fails hidden and the gold patch passes public + hidden."""
    bug_hid, _ = verify(task, root, module_src=task.buggy)
    gold_hid, gold_pub = verify(task, root, module_src=task.gold_patch)
    return {"buggy_fails_hidden": not bug_hid, "gold_passes_public": gold_pub,
            "gold_passes_hidden": gold_hid,
            "fair": (not bug_hid) and gold_pub and gold_hid}
