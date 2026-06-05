"""Graded bugfix benchmark suite (Alpha 23 WS1).

The Alpha-22 smoke fixture is a single trivial divide bug — at ceiling for a strong
vendor harness, so no skill could ever show measurable lift (every live canary held at
lift 0.0). This module replaces it with a *difficulty-stratified* suite: easy / medium /
hard bugfix tasks, each a self-contained repo whose tests fail until the bug is fixed.

Every task ships a reference fix so the suite is provably solvable OFFLINE (see
``apply_reference_fix`` + ``tests/unit/test_benchmark_suite.py``) — we never claim a task
is fair without proving fail -> reference-fix -> pass without any vendor call. Live runs
then measure real capability-by-difficulty and any skill lift honestly: if a harder tier
shows lift the governance loop can promote; if everything is at ceiling that is an honest
finding too.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

DIFFICULTIES = ("easy", "medium", "hard")


@dataclass(frozen=True)
class BenchTask:
    """A single graded bugfix task: a buggy module + a failing test suite + a known fix."""

    name: str
    difficulty: str
    module_path: str            # repo-relative path of the file under test
    buggy: str                  # buggy module source (what the harness sees)
    fixed: str                  # reference fix (offline validation only; never shown)
    test_src: str               # pytest module that fails on buggy, passes on fixed
    prompt: str                 # task instruction given to the harness

    def __post_init__(self) -> None:
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"bad difficulty {self.difficulty}")


_UNIFORM_PROMPT = (
    "There is a bug in {mod}. Fix it so the project's tests pass, then run "
    "`python -m pytest -q` to confirm ALL tests pass before finishing."
)


def _task(name: str, difficulty: str, module_path: str, buggy: str, fixed: str,
          test_src: str) -> BenchTask:
    return BenchTask(name=name, difficulty=difficulty, module_path=module_path,
                     buggy=buggy, fixed=fixed, test_src=test_src,
                     prompt=_UNIFORM_PROMPT.format(mod=module_path))


# --- easy ----------------------------------------------------------------------------
_DIVIDE_BUGGY = "def divide(a, b):\n    return a + b\n"
_DIVIDE_FIXED = "def divide(a, b):\n    return a / b\n"
_DIVIDE_TEST = (
    "from divide import divide\n\n"
    "def test_divide():\n"
    "    assert divide(6, 2) == 3\n"
    "    assert divide(9, 3) == 3\n"
)

_FACT_BUGGY = (
    "def factorial(n):\n"
    "    r = 1\n"
    "    for i in range(1, n):  # bug: stops one short\n"
    "        r *= i\n"
    "    return r\n"
)
_FACT_FIXED = (
    "def factorial(n):\n"
    "    r = 1\n"
    "    for i in range(1, n + 1):\n"
    "        r *= i\n"
    "    return r\n"
)
_FACT_TEST = (
    "from factorial import factorial\n\n"
    "def test_factorial():\n"
    "    assert factorial(0) == 1\n"
    "    assert factorial(1) == 1\n"
    "    assert factorial(3) == 6\n"
    "    assert factorial(5) == 120\n"
)

# --- medium --------------------------------------------------------------------------
_SLUG_BUGGY = (
    "import re\n\n"
    "def slugify(s):\n"
    "    s = s.lower()\n"
    "    s = re.sub(r'[^a-z0-9]+', '-', s)\n"
    "    return s  # bug: does not trim leading/trailing separators or input space\n"
)
_SLUG_FIXED = (
    "import re\n\n"
    "def slugify(s):\n"
    "    s = s.strip().lower()\n"
    "    s = re.sub(r'[^a-z0-9]+', '-', s)\n"
    "    return s.strip('-')\n"
)
_SLUG_TEST = (
    "from slug import slugify\n\n"
    "def test_slugify():\n"
    "    assert slugify('Hello World') == 'hello-world'\n"
    "    assert slugify('  Trim Me  ') == 'trim-me'\n"
    "    assert slugify('a!!!b') == 'a-b'\n"
    "    assert slugify('Already-Slug') == 'already-slug'\n"
)

_CHUNK_BUGGY = (
    "def chunk(xs, n):\n"
    "    out = []\n"
    "    for i in range(0, len(xs) - n, n):  # bug: drops the last partial chunk\n"
    "        out.append(xs[i:i + n])\n"
    "    return out\n"
)
_CHUNK_FIXED = (
    "def chunk(xs, n):\n"
    "    if n <= 0:\n"
    "        raise ValueError('n must be positive')\n"
    "    return [xs[i:i + n] for i in range(0, len(xs), n)]\n"
)
_CHUNK_TEST = (
    "import pytest\n"
    "from chunk import chunk\n\n"
    "def test_chunk():\n"
    "    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]\n"
    "    assert chunk([1, 2, 3], 2) == [[1, 2], [3]]\n"
    "    assert chunk([], 2) == []\n"
    "    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\n"
    "    with pytest.raises(ValueError):\n"
    "        chunk([1, 2, 3], 0)\n"
)

# --- hard ----------------------------------------------------------------------------
_ROMAN_BUGGY = (
    "def to_roman(n):\n"
    "    vals = [(1000, 'M'), (500, 'D'), (100, 'C'), (50, 'L'),\n"
    "            (10, 'X'), (5, 'V'), (1, 'I')]  # bug: no subtractive forms\n"
    "    out = ''\n"
    "    for v, sym in vals:\n"
    "        while n >= v:\n"
    "            out += sym\n"
    "            n -= v\n"
    "    return out\n"
)
_ROMAN_FIXED = (
    "def to_roman(n):\n"
    "    vals = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),\n"
    "            (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),\n"
    "            (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]\n"
    "    out = ''\n"
    "    for v, sym in vals:\n"
    "        while n >= v:\n"
    "            out += sym\n"
    "            n -= v\n"
    "    return out\n"
)
_ROMAN_TEST = (
    "from roman import to_roman\n\n"
    "def test_to_roman():\n"
    "    assert to_roman(1) == 'I'\n"
    "    assert to_roman(4) == 'IV'\n"
    "    assert to_roman(9) == 'IX'\n"
    "    assert to_roman(40) == 'XL'\n"
    "    assert to_roman(90) == 'XC'\n"
    "    assert to_roman(400) == 'CD'\n"
    "    assert to_roman(900) == 'CM'\n"
    "    assert to_roman(1994) == 'MCMXCIV'\n"
)

_MERGE_BUGGY = (
    "def merge_intervals(intervals):\n"
    "    out = []\n"
    "    for a, b in intervals:  # bug: no sort, no overlap merge\n"
    "        out.append((a, b))\n"
    "    return out\n"
)
_MERGE_FIXED = (
    "def merge_intervals(intervals):\n"
    "    if not intervals:\n"
    "        return []\n"
    "    s = sorted(intervals, key=lambda x: x[0])\n"
    "    out = [list(s[0])]\n"
    "    for a, b in s[1:]:\n"
    "        if a <= out[-1][1]:\n"
    "            out[-1][1] = max(out[-1][1], b)\n"
    "        else:\n"
    "            out.append([a, b])\n"
    "    return [tuple(x) for x in out]\n"
)
_MERGE_TEST = (
    "from intervals import merge_intervals\n\n"
    "def test_merge_intervals():\n"
    "    assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]\n"
    "    assert merge_intervals([(1, 4), (4, 5)]) == [(1, 5)]\n"
    "    assert merge_intervals([]) == []\n"
    "    assert merge_intervals([(5, 6), (1, 3), (2, 4)]) == [(1, 4), (5, 6)]\n"
)


BENCH_TASKS: list[BenchTask] = [
    _task("divide", "easy", "divide.py", _DIVIDE_BUGGY, _DIVIDE_FIXED, _DIVIDE_TEST),
    _task("factorial", "easy", "factorial.py", _FACT_BUGGY, _FACT_FIXED, _FACT_TEST),
    _task("slugify", "medium", "slug.py", _SLUG_BUGGY, _SLUG_FIXED, _SLUG_TEST),
    _task("chunk", "medium", "chunk.py", _CHUNK_BUGGY, _CHUNK_FIXED, _CHUNK_TEST),
    _task("roman", "hard", "roman.py", _ROMAN_BUGGY, _ROMAN_FIXED, _ROMAN_TEST),
    _task("merge_intervals", "hard", "intervals.py", _MERGE_BUGGY, _MERGE_FIXED,
          _MERGE_TEST),
]


def _git_init(repo: Path) -> None:
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "init"]):
        subprocess.run(argv, cwd=repo, check=False)


def build_bench_repo(root: Path, task: BenchTask) -> Path:
    """Materialize ``task`` as a git repo with the BUGGY module + its failing tests."""
    repo = root / f"bench_{task.name}"
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / task.module_path).write_text(task.buggy)
    (repo / "tests" / f"test_{task.name}.py").write_text(task.test_src)
    (repo / "tests" / "__init__.py").write_text("")
    # tests import the module by top-level name; make the repo root importable.
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    _git_init(repo)
    return repo


def apply_reference_fix(repo: Path, task: BenchTask) -> None:
    """Overwrite the buggy module with the reference fix (offline validation only)."""
    (repo / task.module_path).write_text(task.fixed)


def run_pytest(repo: Path, timeout_s: int = 120) -> bool:
    """Return True iff the repo's test suite passes."""
    proc = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo,
                          capture_output=True, text=True, timeout=timeout_s, check=False)
    return proc.returncode == 0


def tasks_by_difficulty(difficulty: str) -> list[BenchTask]:
    return [t for t in BENCH_TASKS if t.difficulty == difficulty]
