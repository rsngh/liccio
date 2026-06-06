"""LIVE EVALUATION on UNSEEN inputs — does the control plane work against its purpose?

Independent acceptance test written for the repo evaluation. Unlike the repo's own fixtures
(benchmark_suite / repo_replay), every bug here is AUTHORED FRESH for this evaluation and does
NOT appear anywhere in src/ or tests/ — so neither the model nor the system has memorized it.

For each unseen bug we exercise the FULL moat loop with ONLY the real Claude adapter
registered, so the control plane must: snapshot -> compile context -> route (log
action_probability) -> run the model in an isolated git worktree -> capture diff -> execute
the verification plan (pytest) -> aggregate evidence -> evaluate -> reward -> record provenance.

Three guards make the pass/fail honest:
  1. OFFLINE FAIRNESS: buggy module -> pytest FAILS, reference fix -> pytest PASSES. The
     reference fix is NEVER shown to the agent; it only proves the harness is solvable+fair.
  2. EXECUTION TRUTH: "succeeded" means the control plane actually RAN pytest and it passed.
  3. GENERALIZATION: re-apply the model's captured diff to a HELD-OUT test with inputs the
     model never saw. Passing rules out overfitting to the visible failing test.

Plus two robustness probes:
  - NO-OP: a module that is already correct (no bug). The loop must not regress it.
  - The harness is fully redacted + secret-scanned.

Writes evals/reports/eval_unseen_live.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.observability.live_report import redact_report

MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class UnseenBug:
    name: str
    module_path: str
    issue_text: str       # what a bug reporter would file (the only spec the agent sees)
    buggy: str
    fixed: str            # reference fix — offline fairness proof only, never shown
    visible_test: str     # failing test shipped with the bug report
    holdout_test: str     # SAME bug, DIFFERENT unseen inputs (generalization proof)


# --- 1. exponential backoff that grows linearly --------------------------------------
_BACKOFF = UnseenBug(
    "retry_backoff", "backoff.py",
    "retry_delay(base=1.0, attempt=3) returns 3.0 but exponential backoff should give 8.0 "
    "(base * 2**attempt). Delays are growing linearly, not exponentially, so retries hammer "
    "a failing service instead of backing off.",
    buggy=("def retry_delay(base, attempt):\n"
           "    return base * attempt  # bug: linear, not exponential\n"),
    fixed="def retry_delay(base, attempt):\n    return base * (2 ** attempt)\n",
    visible_test=("from backoff import retry_delay\n\n"
                  "def test_backoff():\n"
                  "    assert retry_delay(1.0, 0) == 1.0\n"
                  "    assert retry_delay(1.0, 3) == 8.0\n"
                  "    assert retry_delay(2.0, 2) == 8.0\n"),
    holdout_test=("from backoff import retry_delay\n\n"
                  "def test_holdout():\n"
                  "    assert retry_delay(1.0, 4) == 16.0\n"
                  "    assert retry_delay(0.5, 3) == 4.0\n"
                  "    assert retry_delay(3.0, 1) == 6.0\n"
                  "    assert retry_delay(1.0, 10) == 1024.0\n"))

# --- 2. duration parser that drops the hours component -------------------------------
_DURATION = UnseenBug(
    "parse_duration", "duration.py",
    "parse_duration('1h30m') returns 1800 but should return 5400 (1*3600 + 30*60). The hours "
    "component is being ignored; only minutes and seconds are summed.",
    buggy=("import re\n\n"
           "def parse_duration(s):\n"
           "    total = 0\n"
           "    m = re.findall(r'(\\d+)([ms])', s)  # bug: 'h' not matched\n"
           "    for value, unit in m:\n"
           "        total += int(value) * (60 if unit == 'm' else 1)\n"
           "    return total\n"),
    fixed=("import re\n\n"
           "def parse_duration(s):\n"
           "    total = 0\n"
           "    factor = {'h': 3600, 'm': 60, 's': 1}\n"
           "    for value, unit in re.findall(r'(\\d+)([hms])', s):\n"
           "        total += int(value) * factor[unit]\n"
           "    return total\n"),
    visible_test=("from duration import parse_duration\n\n"
                  "def test_duration():\n"
                  "    assert parse_duration('1h30m') == 5400\n"
                  "    assert parse_duration('45s') == 45\n"
                  "    assert parse_duration('2h') == 7200\n"),
    holdout_test=("from duration import parse_duration\n\n"
                  "def test_holdout():\n"
                  "    assert parse_duration('1h1m1s') == 3661\n"
                  "    assert parse_duration('10m') == 600\n"
                  "    assert parse_duration('3h') == 10800\n"
                  "    assert parse_duration('90s') == 90\n"))

# --- 3. token-bucket rate limiter that allows bursts over capacity -------------------
_BUCKET = UnseenBug(
    "token_bucket", "bucket.py",
    "TokenBucket(capacity=2) lets through a third request immediately: allow() keeps "
    "returning True past the capacity because it never caps tokens and decrements below zero. "
    "It should allow exactly `capacity` calls until refill() adds tokens back.",
    buggy=("class TokenBucket:\n"
           "    def __init__(self, capacity):\n"
           "        self.capacity = capacity\n        self.tokens = capacity\n\n"
           "    def allow(self):\n"
           "        self.tokens -= 1  # bug: never checks if tokens remain\n"
           "        return True\n\n"
           "    def refill(self, n):\n"
           "        self.tokens += n  # bug: can exceed capacity\n"),
    fixed=("class TokenBucket:\n"
           "    def __init__(self, capacity):\n"
           "        self.capacity = capacity\n        self.tokens = capacity\n\n"
           "    def allow(self):\n"
           "        if self.tokens <= 0:\n            return False\n"
           "        self.tokens -= 1\n        return True\n\n"
           "    def refill(self, n):\n"
           "        self.tokens = min(self.capacity, self.tokens + n)\n"),
    visible_test=("from bucket import TokenBucket\n\n"
                  "def test_bucket():\n"
                  "    b = TokenBucket(2)\n"
                  "    assert b.allow() is True\n    assert b.allow() is True\n"
                  "    assert b.allow() is False\n"
                  "    b.refill(1)\n    assert b.allow() is True\n"
                  "    assert b.allow() is False\n"),
    holdout_test=("from bucket import TokenBucket\n\n"
                  "def test_holdout():\n"
                  "    b = TokenBucket(3)\n"
                  "    assert [b.allow() for _ in range(4)] == [True, True, True, False]\n"
                  "    b.refill(10)\n"                       # capped at capacity
                  "    assert [b.allow() for _ in range(4)] == [True, True, True, False]\n"))

# --- 4. CSV field escaping that doesn't quote separators/quotes ----------------------
_CSV = UnseenBug(
    "csv_escape", "csvfmt.py",
    "csv_field('a,b') returns 'a,b' unquoted, which corrupts the row. A field containing a "
    "comma, a double-quote, or a newline must be wrapped in double-quotes with inner quotes "
    "doubled (RFC 4180).",
    buggy=("def csv_field(value):\n"
           "    return value  # bug: no quoting/escaping at all\n"),
    fixed=("def csv_field(value):\n"
           "    if any(c in value for c in (',', '\"', '\\n')):\n"
           "        return '\"' + value.replace('\"', '\"\"') + '\"'\n"
           "    return value\n"),
    visible_test=("from csvfmt import csv_field\n\n"
                  "def test_csv():\n"
                  "    assert csv_field('plain') == 'plain'\n"
                  "    assert csv_field('a,b') == '\"a,b\"'\n"
                  "    assert csv_field('he said \"hi\"') == '\"he said \"\"hi\"\"\"'\n"),
    holdout_test=("from csvfmt import csv_field\n\n"
                  "def test_holdout():\n"
                  "    assert csv_field('') == ''\n"
                  "    assert csv_field('line1\\nline2') == '\"line1\\nline2\"'\n"
                  "    assert csv_field('1,2,3') == '\"1,2,3\"'\n"
                  "    assert csv_field('no-special') == 'no-special'\n"))

# --- 5. binary search with a boundary / not-found bug --------------------------------
_SEARCH = UnseenBug(
    "jump_search", "search.py",
    "bsearch([1,3,5,7,9], 9) returns -1 but 9 is present at index 4. The high bound is set to "
    "len(arr)-1 yet the loop uses `high = mid - 1` with `while low < high`, so the last "
    "element is never examined. It should find every present element and return -1 only when "
    "absent.",
    buggy=("def bsearch(arr, target):\n"
           "    low, high = 0, len(arr) - 1\n"
           "    while low < high:  # bug: misses the final element\n"
           "        mid = (low + high) // 2\n"
           "        if arr[mid] == target:\n            return mid\n"
           "        if arr[mid] < target:\n            low = mid + 1\n"
           "        else:\n            high = mid - 1\n"
           "    return -1\n"),
    fixed=("def bsearch(arr, target):\n"
           "    low, high = 0, len(arr) - 1\n"
           "    while low <= high:\n"
           "        mid = (low + high) // 2\n"
           "        if arr[mid] == target:\n            return mid\n"
           "        if arr[mid] < target:\n            low = mid + 1\n"
           "        else:\n            high = mid - 1\n"
           "    return -1\n"),
    visible_test=("from search import bsearch\n\n"
                  "def test_search():\n"
                  "    assert bsearch([1, 3, 5, 7, 9], 9) == 4\n"
                  "    assert bsearch([1, 3, 5, 7, 9], 1) == 0\n"
                  "    assert bsearch([1, 3, 5, 7, 9], 4) == -1\n"),
    holdout_test=("from search import bsearch\n\n"
                  "def test_holdout():\n"
                  "    assert bsearch([2, 4, 6, 8], 8) == 3\n"
                  "    assert bsearch([2, 4, 6, 8], 2) == 0\n"
                  "    assert bsearch([5], 5) == 0\n"
                  "    assert bsearch([5], 7) == -1\n"
                  "    assert bsearch([], 1) == -1\n"))

BUGS = [_BACKOFF, _DURATION, _BUCKET, _CSV, _SEARCH]


def _git_init(repo: Path) -> None:
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"],
                 ["git", "config", "commit.gpgsign", "false"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "buggy baseline"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)


def run_pytest(repo: Path, timeout_s: int = 60) -> bool:
    proc = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo, capture_output=True,
                          text=True, timeout=timeout_s, check=False)
    return proc.returncode == 0


def build_repo(root: Path, bug: UnseenBug, *, buggy: bool = True) -> Path:
    repo = root / f"repo_{bug.name}"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / bug.module_path).write_text(bug.buggy if buggy else bug.fixed)
    (repo / f"test_{bug.name}.py").write_text(bug.visible_test)
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
        "[tool.pytest.ini_options]\naddopts = \"-q\"\n")
    (repo / "ISSUE.md").write_text(f"# Bug report\n\n{bug.issue_text}\n")
    _git_init(repo)
    return repo


def reconstruct_module(buggy_src: str, module_path: str, unified_diff: str) -> str:
    if not unified_diff:
        return ""
    if not unified_diff.endswith("\n"):
        unified_diff += "\n"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / module_path).write_text(buggy_src)
        (p / "patch.diff").write_text(unified_diff)
        proc = subprocess.run(["git", "apply", "-p1", "patch.diff"], cwd=p,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(["patch", "-p1", "-i", "patch.diff"], cwd=p,
                           capture_output=True, text=True)
        return (p / module_path).read_text()


def holdout_passes(module_path: str, module_src: str, holdout_test: str) -> bool:
    if not module_src:
        return False
    with tempfile.TemporaryDirectory() as d:
        h = Path(d)
        (h / module_path).write_text(module_src)
        (h / "test_holdout.py").write_text(holdout_test)
        (h / "conftest.py").write_text(
            "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
        return run_pytest(h, timeout_s=60)


def _service(workroot: Path, name: str, registry: AgentRegistry) -> AppService:
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{workroot / f'acp_{name}.db'}",
        artifact_dir=str(workroot / "artifacts"),
        workspace_dir=str(workroot / "workspaces"),
    )
    return AppService(settings=settings, registry=registry)


def run_bug(bug: UnseenBug, workroot: Path) -> dict:
    repo_path = build_repo(workroot, bug, buggy=True)

    # (1) Offline fairness proof.
    buggy_fails = not run_pytest(repo_path)
    (repo_path / bug.module_path).write_text(bug.fixed)
    ref_passes = run_pytest(repo_path)
    (repo_path / bug.module_path).write_text(bug.buggy)
    subprocess.run(["git", "checkout", "-q", "--", bug.module_path], cwd=repo_path,
                   check=False, capture_output=True)

    registry = AgentRegistry()
    registry.register(ClaudeAgentAdapter(name="claude", model=MODEL))
    service = _service(workroot, bug.name, registry)
    repo = service.create_repo(f"demo-{bug.name}", str(repo_path), default_branch="master")
    task = service.create_task(repo.id, title=f"Fix bug in {bug.module_path}",
                               body=bug.issue_text,
                               acceptance_criteria=[f"test_{bug.name}.py passes"])
    state = service.run_task(task.id)
    status = state.status if isinstance(state.status, str) else state.status.value

    diffs = service.run_diff(state.run_id)
    evidence = service.run_evidence(state.run_id)
    evaluation = service.run_evaluation(state.run_id) or {}
    graph = service.full_run_graph(state.run_id)
    attempts = graph.get("attempts", [])
    routed = (graph.get("routing_decision") or {}).get("action", {})
    reward_events = graph.get("reward_events", [])

    unified = diffs[0].get("unified_diff", "") if diffs else ""
    produced = reconstruct_module(bug.buggy, bug.module_path, unified)
    generalizes = holdout_passes(bug.module_path, produced, bug.holdout_test)

    _PASS = {"pass", "passed", "succeeded", "ok"}
    pytest_ev = [e for e in evidence if "pytest" in (
        e.get("name", "") + e.get("summary", "")).lower() or e.get("kind") in (
        "unit_test", "test")]
    verified_green = status == "succeeded" and any(e.get("status") in _PASS for e in pytest_ev)
    attempt = attempts[0] if attempts else {}
    return {
        "bug": bug.name, "module": bug.module_path,
        "offline_fair": {"buggy_fails": buggy_fails, "reference_fix_passes": ref_passes},
        "routed_to": routed.get("agent_name"),
        "context_strategy": routed.get("context_strategy"),
        "action_probability": (graph.get("routing_decision") or {}).get("action_probability"),
        "status": status,
        "verified_green_by_execution": verified_green,
        "generalizes_to_holdout": generalizes,
        "evidence": [f"{e.get('kind')}:{e.get('name')} -> {e.get('status')}" for e in evidence],
        "evaluation": {"spec_compliance": evaluation.get("spec_compliance"),
                       "confidence": evaluation.get("confidence")},
        "reward": (reward_events[-1].get("reward") if reward_events else None),
        "tokens": {"in": attempt.get("input_token_count"),
                   "out": attempt.get("output_token_count")},
        "provenance_complete": all([
            state.snapshot_id, state.context_pack_id, state.routing_decision_id,
            attempt.get("id"), state.evaluation_result_id, state.reward_event_id,
            state.trace_id]),
    }


def run_noop_probe(workroot: Path) -> dict:
    """Robustness: a module that is ALREADY correct. The loop must verify green, not regress."""
    bug = _BACKOFF  # reuse the shape but ship the CORRECT module + a passing test
    repo_path = build_repo(workroot / "noop", bug, buggy=False)
    starts_green = run_pytest(repo_path)
    registry = AgentRegistry()
    registry.register(ClaudeAgentAdapter(name="claude", model=MODEL))
    service = _service(workroot / "noop", f"{bug.name}_noop", registry)
    repo = service.create_repo("demo-noop", str(repo_path), default_branch="master")
    task = service.create_task(
        repo.id, title="No-op: confirm backoff is correct",
        body="Confirm retry_delay implements exponential backoff; the test should already pass.",
        acceptance_criteria=["existing test still passes"])
    state = service.run_task(task.id)
    status = state.status if isinstance(state.status, str) else state.status.value
    diffs = service.run_diff(state.run_id)
    unified = diffs[0].get("unified_diff", "") if diffs else ""
    produced = reconstruct_module(bug.fixed, bug.module_path, unified) or bug.fixed
    still_green = holdout_passes(bug.module_path, produced, bug.visible_test)
    return {"probe": "noop_already_correct", "started_green": starts_green,
            "status": status, "still_green_after_loop": still_green}


def main() -> int:
    key = os.environ.get("ACP_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[skip] no ANTHROPIC key in env")
        return 0
    os.environ["ACP_ANTHROPIC_API_KEY"] = key

    rows = []
    with tempfile.TemporaryDirectory(prefix="acp_unseen_") as d:
        workroot = Path(d)
        for bug in BUGS:
            print(f"\n=== {bug.name} ({bug.module_path}) ===")
            r = run_bug(bug, workroot)
            rows.append(r)
            print(f"  routed={r['routed_to']} status={r['status']} "
                  f"green={r['verified_green_by_execution']} "
                  f"generalizes={r['generalizes_to_holdout']} reward={r['reward']}")
        print("\n=== robustness probe: no-op (already correct) ===")
        noop = run_noop_probe(workroot)
        print(f"  started_green={noop['started_green']} status={noop['status']} "
              f"still_green={noop['still_green_after_loop']}")

    solved = sum(1 for r in rows
                 if r["verified_green_by_execution"] and r["generalizes_to_holdout"])
    fair = all(r["offline_fair"]["buggy_fails"] and r["offline_fair"]["reference_fix_passes"]
               for r in rows)
    report = {
        "experiment": "eval_unseen_live",
        "what": "independent acceptance test: real Claude driven end-to-end by the acp "
                "control plane on bugs AUTHORED FRESH for this evaluation (not in the repo)",
        "model": MODEL,
        "evidence_tier": "fixture-unseen (authored for this eval; absent from src/ and tests/)",
        "n_bugs": len(rows),
        "n_solved_verified_and_generalized": solved,
        "solve_rate": round(solved / len(rows), 4) if rows else 0.0,
        "all_offline_fair": fair,
        "provenance_complete_all": all(r["provenance_complete"] for r in rows),
        "noop_probe": noop,
        "rows": rows,
    }
    out = Path("evals/reports/eval_unseen_live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for env_key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(env_key)
        if secret:
            assert secret not in out.read_text(), f"{env_key} leaked!"
    print(f"\nUNSEEN SOLVE RATE (verified + generalized): {solved}/{len(rows)} | fair={fair}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
