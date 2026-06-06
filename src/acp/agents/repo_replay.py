"""Repo-replay tasks: real-world bug SHAPES, not toy arithmetic (Alpha 29 infra).

The synthetic/hard suites are arithmetic/DP traps; these are bugs that look like real
library issues — semantic versioning string-compare, 1-indexed pagination off-by-one, shallow
config merge, LRU recency, path normalization. Each ships an ISSUE description (what a
reporter would write), a buggy module, a reference fix, and HIDDEN tests (the verifier; not
shown to the generator). Every task is proven offline (buggy fails, fix passes).

HONESTY ON EVIDENCE TIER: these are FIXTURE-tier tasks shaped like real issues — they are NOT
scraped real_repo_replay history (which needs a GitHub issue ingestor + network/auth not
available here). They are a faithful step toward it and the infrastructure (RepoReplayTask +
KnownFixVerifier) a future ingestor would feed. Reports label them tier=fixture accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.agents.benchmark_suite import BenchTask


@dataclass(frozen=True)
class RepoReplayTask:
    name: str
    module_path: str
    issue_text: str          # what a bug reporter would write (the prompt context)
    buggy: str
    fixed: str
    test_src: str            # HIDDEN verifier — not shown to the generator

    def as_bench_task(self) -> BenchTask:
        prompt = (f"Fix the bug described in this issue, then run `python -m pytest -q`.\n\n"
                  f"ISSUE: {self.issue_text}")
        return BenchTask(self.name, "hard", self.module_path, self.buggy, self.fixed,
                         self.test_src, prompt)


_SEMVER = RepoReplayTask(
    "semver_compare", "semver.py",
    "compare_versions('1.10.0', '1.9.0') returns -1 but 1.10 is newer than 1.9. Version "
    "comparison is using string ordering instead of numeric component ordering.",
    buggy=("def compare_versions(a, b):\n"
           "    return (a > b) - (a < b)  # bug: lexicographic string compare\n"),
    fixed=("def compare_versions(a, b):\n"
           "    pa = [int(x) for x in a.split('.')]\n"
           "    pb = [int(x) for x in b.split('.')]\n"
           "    return (pa > pb) - (pa < pb)\n"),
    test_src=("from semver import compare_versions\n\n"
              "def test_semver():\n"
              "    assert compare_versions('1.10.0', '1.9.0') == 1\n"
              "    assert compare_versions('1.0.0', '1.0.0') == 0\n"
              "    assert compare_versions('2.0.0', '10.0.0') == -1\n"
              "    assert compare_versions('1.2.3', '1.2.10') == -1\n"))

_PAGINATE = RepoReplayTask(
    "paginate", "paging.py",
    "paginate(items, page=1, per_page=2) returns the SECOND page, not the first. Pages are "
    "1-indexed in our API but the slice math treats page as 0-indexed.",
    buggy=("def paginate(items, page, per_page):\n"
           "    start = page * per_page  # bug: page is 1-indexed\n"
           "    return items[start:start + per_page]\n"),
    fixed=("def paginate(items, page, per_page):\n"
           "    if page < 1:\n        raise ValueError('page is 1-indexed')\n"
           "    start = (page - 1) * per_page\n"
           "    return items[start:start + per_page]\n"),
    test_src=("import pytest\nfrom paging import paginate\n\n"
              "def test_paginate():\n"
              "    assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]\n"
              "    assert paginate([1, 2, 3, 4, 5], 2, 2) == [3, 4]\n"
              "    assert paginate([1, 2, 3, 4, 5], 3, 2) == [5]\n"
              "    with pytest.raises(ValueError):\n        paginate([1], 0, 2)\n"))

_MERGE = RepoReplayTask(
    "deep_merge", "config.py",
    "deep_merge of two config dicts loses keys: merging {'db': {'host': 'x', 'port': 5}} "
    "with {'db': {'port': 6}} drops 'host'. Nested dicts are being overwritten, not merged.",
    buggy=("def deep_merge(base, override):\n"
           "    result = dict(base)\n"
           "    result.update(override)  # bug: nested dicts overwritten, not merged\n"
           "    return result\n"),
    fixed=("def deep_merge(base, override):\n"
           "    result = dict(base)\n"
           "    for k, v in override.items():\n"
           "        if isinstance(v, dict) and isinstance(result.get(k), dict):\n"
           "            result[k] = deep_merge(result[k], v)\n"
           "        else:\n            result[k] = v\n"
           "    return result\n"),
    test_src=("from config import deep_merge\n\n"
              "def test_deep_merge():\n"
              "    assert deep_merge({'db': {'host': 'x', 'port': 5}}, "
              "{'db': {'port': 6}}) == {'db': {'host': 'x', 'port': 6}}\n"
              "    assert deep_merge({'a': 1}, {'b': 2}) == {'a': 1, 'b': 2}\n"
              "    assert deep_merge({'a': {'b': {'c': 1}}}, {'a': {'b': {'d': 2}}}) == "
              "{'a': {'b': {'c': 1, 'd': 2}}}\n"))

_LRU = RepoReplayTask(
    "lru_cache", "cache.py",
    "Our LRUCache evicts the wrong entry: reading a key with get() should mark it as recently "
    "used, but eviction still removes it. get() does not update recency.",
    buggy=("class LRUCache:\n"
           "    def __init__(self, capacity):\n"
           "        self.capacity = capacity\n        self.store = {}\n\n"
           "    def get(self, key):\n"
           "        return self.store.get(key)  # bug: does not update recency\n\n"
           "    def put(self, key, value):\n"
           "        if key not in self.store and len(self.store) >= self.capacity:\n"
           "            self.store.pop(next(iter(self.store)))\n"
           "        self.store[key] = value\n"),
    fixed=("from collections import OrderedDict\n\n"
           "class LRUCache:\n"
           "    def __init__(self, capacity):\n"
           "        self.capacity = capacity\n        self.store = OrderedDict()\n\n"
           "    def get(self, key):\n"
           "        if key not in self.store:\n            return None\n"
           "        self.store.move_to_end(key)\n        return self.store[key]\n\n"
           "    def put(self, key, value):\n"
           "        if key in self.store:\n            self.store.move_to_end(key)\n"
           "        elif len(self.store) >= self.capacity:\n"
           "            self.store.popitem(last=False)\n"
           "        self.store[key] = value\n"),
    test_src=("from cache import LRUCache\n\n"
              "def test_lru():\n"
              "    c = LRUCache(2)\n    c.put('a', 1)\n    c.put('b', 2)\n"
              "    assert c.get('a') == 1  # 'a' now most-recently used\n"
              "    c.put('c', 3)           # should evict 'b', not 'a'\n"
              "    assert c.get('b') is None\n    assert c.get('a') == 1\n"
              "    assert c.get('c') == 3\n"))

_PATHNORM = RepoReplayTask(
    "normalize_path", "paths.py",
    "normalize_path('a/b/../c') should give 'a/c' and normalize_path('a/./b') should give "
    "'a/b'. Current code crashes on '..' that pops past the root and keeps '.' segments.",
    buggy=("def normalize_path(path):\n"
           "    parts = []\n"
           "    for p in path.split('/'):\n"
           "        if p == '..':\n            parts.pop()  # bug: crashes when empty\n"
           "        else:\n            parts.append(p)        # bug: keeps '' and '.'\n"
           "    return '/'.join(parts)\n"),
    fixed=("def normalize_path(path):\n"
           "    parts = []\n"
           "    for p in path.split('/'):\n"
           "        if p in ('', '.'):\n            continue\n"
           "        if p == '..':\n"
           "            if parts:\n                parts.pop()\n"
           "        else:\n            parts.append(p)\n"
           "    return '/'.join(parts)\n"),
    test_src=("from paths import normalize_path\n\n"
              "def test_normalize():\n"
              "    assert normalize_path('a/b/../c') == 'a/c'\n"
              "    assert normalize_path('a/./b') == 'a/b'\n"
              "    assert normalize_path('../a') == 'a'\n"
              "    assert normalize_path('a//b') == 'a/b'\n"))


REPLAY_TASKS: list[RepoReplayTask] = [_SEMVER, _PAGINATE, _MERGE, _LRU, _PATHNORM]
