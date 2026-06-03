"""WS6 live experiment — real harness activation/adherence metrics (uses keys).

Runs the real openai_harness + claude_harness on no-patch tasks, builds normalized
AgentTraces from the actual tool loops, verifies each by running the repo's tests,
and computes REAL harness-benefit metrics (HAR/HFR/PWL) from observed behavior —
not synthetic. Writes redacted ``reports/live/alpha12_harness_metrics.json``.

Skips cleanly without keys; defensive per attempt.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from git import Repo

from acp.agents.trace import build_agent_trace
from acp.evaluation.harness_metrics import (
    activation_report,
    adherence_report,
    harness_benefit_metrics,
)
from acp.observability.live_report import redact_report
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

OUT = Path("reports/live/alpha12_harness_metrics.json")
TASKS = [
    {"id": "divide", "files": {"calculator.py":
                               "def divide(a, b):\n    if b == 0:\n        return 0\n"
                               "    return a / b\n"},
     "test": "test_c.py", "test_src":
         "import pytest\nfrom calculator import divide\n\ndef test():\n    "
         "with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n",
     "title": "Fix divide by zero", "body": "make divide() raise ZeroDivisionError on b==0",
     "type": "bugfix"},
    {"id": "factorial", "files": {"m.py": "def factorial(n):\n    pass\n"},
     "test": "test_m.py", "test_src":
         "from m import factorial\n\ndef test():\n    assert factorial(5) == 120\n",
     "title": "Implement factorial", "body": "implement factorial(n) in m.py",
     "type": "feature"},
]


def _build_harnesses() -> dict:
    out: dict = {}
    if os.environ.get("OPENAI_API_KEY"):
        os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
        from acp.agents.openai_harness import OpenAIHarnessAdapter
        a = OpenAIHarnessAdapter(max_steps=8)
        if asyncio.run(a.healthcheck()).available:
            out["openai_harness"] = a
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
        from acp.agents.claude_harness import ClaudeHarnessAdapter
        a = ClaudeHarnessAdapter(max_steps=8)
        if asyncio.run(a.healthcheck()).available:
            out["claude_harness"] = a
    return out


def _verify(ws_path: Path, test: str) -> bool:
    try:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", "-q", test], cwd=str(ws_path),
            capture_output=True, timeout=60).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    from acp.core.config import reset_settings

    harnesses = _build_harnesses()
    if not harnesses:
        print("[skip] no harness available (set OPENAI_API_KEY / ANTHROPIC_API_KEY)")
        return 0
    tmp = Path(tempfile.mkdtemp())
    traces = []
    solved: dict[str, bool] = {}
    per_attempt = []
    for spec in TASKS:
        src = tmp / f"repo_{spec['id']}"
        src.mkdir()
        for n, c in spec["files"].items():
            (src / n).write_text(c)
        (src / spec["test"]).write_text(spec["test_src"])
        (src / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
        r = Repo.init(src)
        r.config_writer().set_value("user", "name", "t").release()
        r.config_writer().set_value("user", "email", "t@e.com").release()
        r.index.add(list(spec["files"]) + [spec["test"], "pyproject.toml"])
        r.index.commit("init")
        repo = Repository(name=spec["id"], local_path=str(src), default_branch="master")
        for name, adapter in harnesses.items():
            reset_settings()
            base = Repo(repo.local_path).head.commit.hexsha
            ws = LocalWorkspaceManager(tmp / f"ws_{spec['id']}_{name}").create(
                repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
            target = next(iter(spec["files"]))
            task = Task(repo_id=repo.id, title=spec["title"], body=spec["body"])
            pack = ContextPack(repo_id=repo.id, task_id=task.id, snapshot_id="s",
                               items=[ContextItem(kind="file_chunk", path=target,
                                                  content=(ws.path / target).read_text())])
            t0 = time.time()
            try:
                result = asyncio.run(adapter.execute(task, pack, ws, Budget(
                    max_cost_usd=0.5, max_wall_time_s=120)))
            except Exception:  # noqa: BLE001
                continue
            attempt = AgentAttempt(task_id=task.id, agent_kind=adapter.kind,
                                   agent_name=name)
            trace = build_agent_trace(attempt, result, is_harness=True, task_id=task.id)
            trace.metadata["task_type"] = spec["type"]
            traces.append(trace)
            solved[trace.attempt_id] = _verify(ws.path, spec["test"])
            act = activation_report(trace)
            adh = adherence_report(trace)
            per_attempt.append({
                "adapter": name, "task_type": spec["type"],
                "activated": act.activated, "followed": adh.followed,
                "phase_adherence": adh.phase_adherence,
                "solved": solved[trace.attempt_id],
                "tool_calls": trace.tool_calls, "latency_s": round(time.time() - t0, 2),
            })
            print(f"  {spec['id']:10s} {name:16s} activated={act.activated} "
                  f"followed={adh.followed} solved={solved[trace.attempt_id]}")

    metrics = harness_benefit_metrics(traces, solved)
    report = {"experiment": "alpha12_live_harness_metrics",
              "source": "REAL observed harness traces",
              "benefit_metrics": metrics.model_dump(mode="json"),
              "per_attempt": per_attempt}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        s = os.environ.get(key)
        if s:
            assert s not in OUT.read_text(), f"{key} leaked!"
    print(f"HAR={metrics.har} HFR={metrics.hfr} PWL={metrics.pwl} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
