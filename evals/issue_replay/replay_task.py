# ruff: noqa: E501  (data-heavy fixture file: inline gold patches/tests read better unwrapped)
"""Issue-replay task model + frozen bundles (GOALS Alpha 44 P1).

A first-class evaluation source shaped like real GitHub issue→fixing-PR replay: base SHA fails
public tests, a gold fix passes public + hidden, and the agent's output is judged by hidden
tests + patch-equivalence — never by seeing the gold patch.

HONEST EVIDENCE TIER: this environment has no network/auth, so these are FROZEN SYNTHETIC-REALISTIC
bundles (``source = frozen_synthetic``), not scraped history (``source = real_issue_replay``).
The schema + runner are exactly what an online ingestor would feed; reports label the tier so a
synthetic bundle can never masquerade as real issue-replay evidence. Online ingest is a
network-gated stub here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IssueReplayTask:
    repo_name: str
    base_sha: str
    issue_title: str
    issue_body: str
    module_path: str
    buggy: str                       # repo state at base_sha (public tests fail)
    gold_patch: str                  # the fixing-PR module content (never shown to the agent)
    public_test: str
    hidden_test: str
    task_type: str = "bugfix"
    risk_level: str = "medium"
    context_need: str = "none"
    difficulty_band: str = "medium"
    source: str = "frozen_synthetic"  # frozen_synthetic | real_issue_replay
    extra_files: dict[str, str] = field(default_factory=dict)
    leakage_notes: str = "gold patch withheld from agent; hidden tests held out"

    @property
    def gold_patch_hash(self) -> str:
        return hashlib.sha256(self.gold_patch.encode()).hexdigest()[:16]


# A small set of frozen, realistic issue→fix bundles (distinct bug shapes seen in real repos).
def frozen_bundles() -> list[IssueReplayTask]:
    out: list[IssueReplayTask] = []
    out.append(IssueReplayTask(
        repo_name="acme/dates", base_sha="a1b2c3", context_need="exact_symbol",
        issue_title="parse_iso drops the timezone offset",
        issue_body="parse_iso('2024-01-01T00:00:00+05:00') ignores +05:00 and returns naive minutes.",
        module_path="dates.py",
        buggy="import re\n\ndef offset_minutes(s):\n    m = re.search(r'T..:..', s)\n    return 0  # bug: never parses the offset\n",
        gold_patch="import re\n\ndef offset_minutes(s):\n    m = re.search(r'([+-])(\\d{2}):(\\d{2})$', s)\n    if not m:\n        return 0\n    sign = 1 if m.group(1) == '+' else -1\n    return sign * (int(m.group(2)) * 60 + int(m.group(3)))\n",
        public_test="from dates import offset_minutes\n\ndef test_pub():\n    assert offset_minutes('2024-01-01T00:00:00+05:00') == 300\n",
        hidden_test="from dates import offset_minutes\n\ndef test_hid():\n    assert offset_minutes('x-03:30') == -210\n    assert offset_minutes('xZ') == 0\n    assert offset_minutes('x+00:00') == 0\n"))
    out.append(IssueReplayTask(
        repo_name="acme/cache", base_sha="d4e5f6", context_need="exact_symbol", risk_level="medium",
        issue_title="LRU evicts the most-recently-used entry",
        issue_body="get() should mark a key recently used; eviction removes the wrong entry.",
        module_path="lru.py",
        buggy="class LRU:\n    def __init__(self, cap):\n        self.cap=cap; self.d={}\n    def get(self,k):\n        return self.d.get(k)\n    def put(self,k,v):\n        if k not in self.d and len(self.d)>=self.cap:\n            self.d.pop(next(iter(self.d)))\n        self.d[k]=v\n",
        gold_patch="from collections import OrderedDict\n\nclass LRU:\n    def __init__(self, cap):\n        self.cap=cap; self.d=OrderedDict()\n    def get(self,k):\n        if k not in self.d: return None\n        self.d.move_to_end(k); return self.d[k]\n    def put(self,k,v):\n        if k in self.d: self.d.move_to_end(k)\n        elif len(self.d)>=self.cap: self.d.popitem(last=False)\n        self.d[k]=v\n",
        public_test="from lru import LRU\n\ndef test_pub():\n    c=LRU(2); c.put('a',1); c.put('b',2); assert c.get('a')==1\n    c.put('c',3); assert c.get('b') is None\n",
        hidden_test="from lru import LRU\n\ndef test_hid():\n    c=LRU(2); c.put('a',1); c.put('b',2); c.get('a'); c.put('c',3)\n    assert c.get('a')==1 and c.get('c')==3 and c.get('b') is None\n"))
    out.append(IssueReplayTask(
        repo_name="acme/billing", base_sha="998877", context_need="cross_file_api", risk_level="medium",
        issue_title="invoice total ignores the configured tax rate",
        issue_body="total() hardcodes 0; it must use the configured rate from the settings module.",
        module_path="invoice.py",
        buggy="def total(amount):\n    return amount  # bug: no tax applied\n",
        gold_patch="from settings import tax_rate\n\ndef total(amount):\n    return round(amount * (1 + tax_rate()), 2)\n",
        public_test="from invoice import total\n\ndef test_pub():\n    assert total(100) == 108.5\n",
        hidden_test="from invoice import total\n\ndef test_hid():\n    assert total(0) == 0.0\n    assert total(200) == 217.0\n",
        extra_files={"settings.py": "def tax_rate():\n    return 0.085\n"}))
    out.append(IssueReplayTask(
        repo_name="acme/web", base_sha="abcd12", context_need="exact_symbol", task_type="security_fix",
        risk_level="high", issue_title="open redirect in build_redirect",
        issue_body="build_redirect allows absolute external URLs; only same-site paths should be allowed.",
        module_path="redir.py",
        buggy="def build_redirect(target):\n    return target  # bug: open redirect\n",
        gold_patch="def build_redirect(target):\n    if target.startswith('/') and not target.startswith('//'):\n        return target\n    return '/'\n",
        public_test="from redir import build_redirect\n\ndef test_pub():\n    assert build_redirect('/home') == '/home'\n",
        hidden_test="from redir import build_redirect\n\ndef test_hid():\n    assert build_redirect('https://evil.com') == '/'\n    assert build_redirect('//evil.com') == '/'\n"))
    # a few off-by-one / boundary issues, the most common real bug class
    boundaries = [
        ("acme/pager", "paginate", "def paginate(xs, p, n):\n    return xs[p*n:(p+1)*n]  # 1-indexed off-by-one\n",
         "def paginate(xs, p, n):\n    return xs[(p-1)*n:p*n]\n",
         "    assert paginate(list(range(10)), 1, 3) == [0,1,2]\n",
         "    assert paginate(list(range(10)), 2, 3) == [3,4,5]\n    assert paginate(list(range(10)), 4, 3) == [9]\n"),
        ("acme/ranges", "clamp", "def clamp(x, lo, hi):\n    return x  # bug: no clamp\n",
         "def clamp(x, lo, hi):\n    return max(lo, min(hi, x))\n",
         "    assert clamp(9, 0, 3) == 3\n", "    assert clamp(-9, -2, 2) == -2\n    assert clamp(1, 0, 3) == 1\n"),
    ]
    for repo, fn, buggy, gold, pub, hid in boundaries:
        out.append(IssueReplayTask(
            repo_name=repo, base_sha=hashlib.sha256(repo.encode()).hexdigest()[:6],
            context_need="exact_symbol", issue_title=f"{fn} off-by-one / boundary bug",
            issue_body=f"{fn} returns wrong results at the boundary; see the failing test.",
            module_path=f"{fn}.py", buggy=buggy, gold_patch=gold,
            public_test=f"from {fn} import {fn}\n\ndef test_pub():\n{pub}",
            hidden_test=f"from {fn} import {fn}\n\ndef test_hid():\n{hid}"))
    return out
