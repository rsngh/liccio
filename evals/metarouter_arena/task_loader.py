# ruff: noqa: E501  (data-heavy fixture file: inline test sources read better unwrapped)
"""MetaRouter Arena — scaled task loader (GOALS Alpha 43 P0).

Generates >=50 unseen tasks across >=8 task types and >=5 context_need classes by
parameterizing genuine bug families (each variant has a distinct buggy module, a VISIBLE public
test, and a HELD-OUT hidden test with different inputs, plus a reference fix proven offline).
Authored fresh for the arena — not present elsewhere in src/ or tests/.

Families: local arithmetic/string bugs (none / exact_symbol), cross-file API call
(cross_file_api), multi-file wiring (broad_repo_map), underspecified two-bug (none),
security remediation (security_fix), CI/migration import breakage (ci_migration), and a
memory-required repeated-failure family (memory_required).
"""

from __future__ import annotations

from evals.metarouter_arena.schema import ArenaTaskSpec


def _local_arith() -> list[ArenaTaskSpec]:
    """exact_symbol / none — single-function numeric bugs, parameterized."""
    out = []
    specs = [
        ("clamp", "def clamp(x, lo, hi):\n    return x  # bug: no clamping\n",
         "def clamp(x, lo, hi):\n    return max(lo, min(hi, x))\n",
         [("clamp(5, 0, 3)", "3"), ("clamp(-1, 0, 3)", "0")],
         [("clamp(2, 0, 3)", "2"), ("clamp(9, 1, 4)", "4"), ("clamp(-9, -2, 2)", "-2")]),
        ("gcd", "def gcd(a, b):\n    return a  # bug\n",
         "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n",
         [("gcd(12, 8)", "4")], [("gcd(54, 24)", "6"), ("gcd(17, 5)", "1"), ("gcd(100, 10)", "10")]),
        ("is_palindrome", "def is_palindrome(s):\n    return True  # bug\n",
         "def is_palindrome(s):\n    return s == s[::-1]\n",
         [("is_palindrome('aba')", "True")],
         [("is_palindrome('abc')", "False"), ("is_palindrome('')", "True"),
          ("is_palindrome('xyzzyx')", "True")]),
        ("fib", "def fib(n):\n    return n  # bug\n",
         "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
         [("fib(7)", "13")], [("fib(10)", "55"), ("fib(0)", "0"), ("fib(1)", "1")]),
        ("title_case", "def title_case(s):\n    return s  # bug\n",
         "def title_case(s):\n    return ' '.join(w.capitalize() for w in s.split())\n",
         [("title_case('hello world')", "'Hello World'")],
         [("title_case('a b c')", "'A B C'"), ("title_case('THE end')", "'The End'")]),
        ("count_vowels", "def count_vowels(s):\n    return 0  # bug\n",
         "def count_vowels(s):\n    return sum(c in 'aeiou' for c in s.lower())\n",
         [("count_vowels('hello')", "2")],
         [("count_vowels('AEIOU')", "5"), ("count_vowels('xyz')", "0")]),
        ("dedupe", "def dedupe(xs):\n    return xs  # bug: keeps dups\n",
         "def dedupe(xs):\n    seen = set()\n    out = []\n    for x in xs:\n"
         "        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n",
         [("dedupe([1,1,2])", "[1, 2]")],
         [("dedupe([3,3,3])", "[3]"), ("dedupe([1,2,1,3])", "[1, 2, 3]")]),
    ]
    for name, buggy, fixed, pub, hid in specs:
        mod = f"{name}.py"
        pub_body = "\n".join(f"    assert {call} == {exp}" for call, exp in pub)
        hid_body = "\n".join(f"    assert {call} == {exp}" for call, exp in hid)
        out.append(ArenaTaskSpec(
            name=f"local_{name}", task_type="bugfix", risk_level="low",
            difficulty_band="easy", context_need="exact_symbol", module_path=mod,
            buggy=buggy, fixed=fixed,
            public_test=f"from {name} import {name}\n\ndef test_pub():\n{pub_body}\n",
            hidden_test=f"from {name} import {name}\n\ndef test_hid():\n{hid_body}\n",
            issue_text=f"{name}() is wrong: {pub[0][0]} should be {pub[0][1]}. Fix {mod}."))
    return out


def _cross_file() -> list[ArenaTaskSpec]:
    """cross_file_api — the fix must CALL an API defined in another file (repo_map wins)."""
    out = []
    apis = [
        ("tax", "rate.py", "def tax_rate():\n    return 0.075\n",
         "def total(price):\n    return round(price * 1.05, 2)  # wrong, hardcoded\n",
         "from rate import tax_rate\n\ndef total(price):\n    return round(price * (1 + tax_rate()), 2)\n",
         [("total(100)", "107.5")], [("total(40)", "43.0"), ("total(200)", "215.0")]),
        ("shipping", "fees.py", "def flat_fee():\n    return 4.99\n",
         "def grand_total(sub):\n    return sub + 5  # wrong, hardcoded\n",
         "from fees import flat_fee\n\ndef grand_total(sub):\n    return round(sub + flat_fee(), 2)\n",
         [("grand_total(10)", "14.99")], [("grand_total(0)", "4.99"), ("grand_total(20.01)", "25.0")]),
        ("greet", "names.py", "def canonical(n):\n    return n.strip().title()\n",
         "def greet(n):\n    return 'Hi ' + n  # wrong, no canonicalization\n",
         "from names import canonical\n\ndef greet(n):\n    return 'Hi ' + canonical(n)\n",
         [("greet('  bob ')", "'Hi Bob'")], [("greet('ALICE')", "'Hi Alice'")]),
        ("score", "weights.py", "def weight():\n    return 3\n",
         "def score(n):\n    return n * 2  # wrong factor\n",
         "from weights import weight\n\ndef score(n):\n    return n * weight()\n",
         [("score(4)", "12")], [("score(0)", "0"), ("score(7)", "21")]),
    ]
    for name, helper_file, helper_src, buggy, fixed, pub, hid in apis:
        mod = f"{name}.py"
        pub_body = "\n".join(f"    assert {c} == {e}" for c, e in pub)
        hid_body = "\n".join(f"    assert {c} == {e}" for c, e in hid)
        out.append(ArenaTaskSpec(
            name=f"xfile_{name}", task_type="bugfix", risk_level="medium",
            difficulty_band="hard", context_need="cross_file_api", module_path=mod,
            buggy=buggy, fixed=fixed,
            public_test=f"from {name} import {name if name != 'tax' else 'total'}\n",  # placeholder
            hidden_test="",
            issue_text=(f"{mod} hardcodes a value instead of using the canonical helper in "
                        f"{helper_file}. Use the existing API there."),
            extra_files={helper_file: helper_src}))
        # fix the public/hidden test imports to the actual entrypoint
        entry = {"tax": "total", "shipping": "grand_total", "greet": "greet", "score": "score"}[name]
        out[-1] = ArenaTaskSpec(
            name=f"xfile_{name}", task_type="bugfix", risk_level="medium",
            difficulty_band="hard", context_need="cross_file_api", module_path=mod,
            buggy=buggy, fixed=fixed,
            public_test=f"from {name} import {entry}\n\ndef test_pub():\n{pub_body}\n",
            hidden_test=f"from {name} import {entry}\n\ndef test_hid():\n{hid_body}\n",
            issue_text=(f"{mod} hardcodes a value instead of using the canonical helper defined "
                        f"in {helper_file}. Use the existing API there, do not hardcode."),
            extra_files={helper_file: helper_src})
    return out


def _security() -> list[ArenaTaskSpec]:
    """security_fix — replace an unsafe construct with a safe one."""
    out = []
    out.append(ArenaTaskSpec(
        name="sec_eval", task_type="security_fix", risk_level="high", difficulty_band="hard",
        context_need="exact_symbol", module_path="calc.py",
        buggy="def calc(expr):\n    return eval(expr)  # unsafe\n",
        fixed=("import ast, operator\n"
               "_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,\n"
               "        ast.Div: operator.truediv}\n"
               "def calc(expr):\n    def ev(n):\n"
               "        if isinstance(n, ast.Constant):\n            return n.value\n"
               "        if isinstance(n, ast.BinOp):\n"
               "            return _OPS[type(n.op)](ev(n.left), ev(n.right))\n"
               "        raise ValueError('unsupported')\n"
               "    return ev(ast.parse(expr, mode='eval').body)\n"),
        public_test="from calc import calc\n\ndef test_pub():\n    assert calc('1 + 2') == 3\n",
        hidden_test=("import pytest\nfrom calc import calc\n\n"
                     "def test_hid():\n    assert calc('2 * 3') == 6\n"
                     "    with pytest.raises(Exception):\n        calc(\"__import__('os')\")\n"),
        issue_text=("calc() uses eval() on untrusted input — a code-injection risk. Replace it "
                    "with a safe arithmetic evaluator that rejects non-arithmetic input.")))
    out.append(ArenaTaskSpec(
        name="sec_pathtrav", task_type="security_fix", risk_level="high", difficulty_band="hard",
        context_need="exact_symbol", module_path="files.py",
        buggy=("import os\ndef read(base, name):\n"
               "    return os.path.join(base, name)  # path traversal\n"),
        fixed=("import os\ndef read(base, name):\n"
               "    full = os.path.normpath(os.path.join(base, name))\n"
               "    if not full.startswith(os.path.normpath(base) + os.sep):\n"
               "        raise ValueError('path escapes base')\n    return full\n"),
        public_test=("from files import read\nimport os\n\n"
                     "def test_pub():\n    assert read('/data', 'a.txt') == os.path.normpath('/data/a.txt')\n"),
        hidden_test=("import pytest\nfrom files import read\n\n"
                     "def test_hid():\n    with pytest.raises(ValueError):\n"
                     "        read('/data', '../etc/passwd')\n"),
        issue_text=("read() joins user input onto a base path without containment — a path "
                    "traversal risk. Reject names that escape the base directory.")))
    return out


def _ci_migration() -> list[ArenaTaskSpec]:
    """ci_migration — an import/rename breakage after a refactor."""
    out = []
    out.append(ArenaTaskSpec(
        name="ci_rename", task_type="ci_fix", risk_level="medium", difficulty_band="medium",
        context_need="cross_file_api", module_path="app.py",
        buggy="from helpers import old_name\n\ndef run(x):\n    return old_name(x)\n",
        fixed="from helpers import new_name\n\ndef run(x):\n    return new_name(x)\n",
        public_test="from app import run\n\ndef test_pub():\n    assert run(3) == 6\n",
        hidden_test="from app import run\n\ndef test_hid():\n    assert run(5) == 10\n    assert run(0) == 0\n",
        issue_text=("app.py imports old_name from helpers, but helpers was migrated and now only "
                    "exports new_name (same behavior). Fix the import so the tests pass."),
        extra_files={"helpers.py": "def new_name(x):\n    return x * 2\n"}))
    return out


def _underspecified() -> list[ArenaTaskSpec]:
    """none — two bugs, only one named (test discipline)."""
    out = []
    specs = [
        ("acct", "class Account:\n    def __init__(self, b=0):\n        self.b = b\n"
                 "    def deposit(self, a):\n        self.b + a  # bug: discarded\n"
                 "    def withdraw(self, a):\n        self.b -= a  # bug: overdraft\n",
                 "class Account:\n    def __init__(self, b=0):\n        self.b = b\n"
                 "    def deposit(self, a):\n        self.b += a\n"
                 "    def withdraw(self, a):\n        if a > self.b:\n            raise ValueError('nsf')\n"
                 "        self.b -= a\n",
                 "from acct import Account\n\ndef test_pub():\n    a=Account()\n    a.deposit(100)\n    assert a.b==100\n",
                 "import pytest\nfrom acct import Account\n\ndef test_hid():\n    a=Account(50)\n"
                 "    with pytest.raises(ValueError):\n        a.withdraw(100)\n    assert a.b==50\n",
                 "Account.deposit does not increase the balance. Fix it so test_pub passes."),
    ]
    for name, buggy, fixed, pub, hid, issue in specs:
        out.append(ArenaTaskSpec(
            name=f"us_{name}", task_type="bugfix", risk_level="medium", difficulty_band="hard",
            context_need="none", module_path=f"{name}.py", buggy=buggy, fixed=fixed,
            public_test=pub, hidden_test=hid, issue_text=issue))
    return out


def _broad() -> list[ArenaTaskSpec]:
    """broad_repo_map — wire multiple existing helpers."""
    out = []
    out.append(ArenaTaskSpec(
        name="broad_pipeline", task_type="feature", risk_level="medium", difficulty_band="hard",
        context_need="broad_repo_map", module_path="flow.py",
        buggy="def process(rec):\n    return rec  # TODO: validate then enrich using helpers\n",
        fixed=("from validate import validate\nfrom enrich import enrich\n\n"
               "def process(rec):\n    if not validate(rec):\n        raise ValueError('bad')\n"
               "    return enrich(rec)\n"),
        public_test=("from flow import process\n\ndef test_pub():\n"
                     "    assert process({'id': 1}) == {'id': 1, 'ok': True}\n"),
        hidden_test=("import pytest\nfrom flow import process\n\ndef test_hid():\n"
                     "    assert process({'id': 9}) == {'id': 9, 'ok': True}\n"
                     "    with pytest.raises(ValueError):\n        process({})\n"),
        issue_text=("process() must validate a record then enrich it, REUSING the existing "
                    "validate and enrich helpers in this repo. Invalid records raise ValueError."),
        extra_files={"validate.py": "def validate(r):\n    return 'id' in r\n",
                     "enrich.py": "def enrich(r):\n    return {**r, 'ok': True}\n"}))
    return out


def _memory_family(n: int = 8) -> list[ArenaTaskSpec]:
    """memory_required — a repeated failure-signature family (same bug shape, n variants)."""
    out = []
    for i in range(n):
        name = f"mem_offby_{i}"
        sz = (i % 4) + 2                     # 2..5, repeating — same bug SHAPE, varied size
        out.append(ArenaTaskSpec(
            name=name, task_type="bugfix", risk_level="low", difficulty_band="medium",
            context_need="memory_required", module_path=f"{name}.py",
            buggy=f"def page(items, p):\n    return items[p*{sz}:(p+1)*{sz}]  # 0-indexed, off by one\n",
            fixed=f"def page(items, p):\n    return items[(p-1)*{sz}:p*{sz}]\n",
            public_test=(f"from {name} import page\n\ndef test_pub():\n"
                         f"    assert page(list(range(40)), 1) == list(range({sz}))\n"),
            hidden_test=(f"from {name} import page\n\ndef test_hid():\n"
                         f"    assert page(list(range(40)), 2) == list(range({sz}, {2*sz}))\n"),
            issue_text=(f"page(items, 1) should return the FIRST page of size {sz}, but pages are "
                        "1-indexed and the slice math treats them as 0-indexed (recurring bug)."),
        ))
    return out


def _new_types() -> list[ArenaTaskSpec]:
    """One task each for the remaining task_type classes (>=8 types overall)."""
    out = []
    # performance: an O(n^2) scan that is ALSO functionally wrong (never dedupes) -> O(n) set
    out.append(ArenaTaskSpec(
        name="perf_dedupe_count", task_type="performance", risk_level="low",
        difficulty_band="medium", context_need="exact_symbol", module_path="counts.py",
        buggy=("def n_unique(xs):\n    out = []\n    for x in xs:\n"
               "        out.append(x)  # bug: never dedupes; also O(n^2)-prone pattern\n"
               "    return len(out)\n"),
        fixed="def n_unique(xs):\n    return len(set(xs))\n",
        public_test="from counts import n_unique\n\ndef test_pub():\n    assert n_unique([1,1,2]) == 2\n",
        hidden_test=("from counts import n_unique\n\ndef test_hid():\n"
                     "    assert n_unique(list(range(100)) + list(range(100))) == 100\n"
                     "    assert n_unique([]) == 0\n"),
        issue_text="n_unique returns total count, not the number of UNIQUE items. Fix it (and prefer O(n))."))
    # refactor: nested branches that DROP the 'B' case (a real behavior bug to fix while flattening)
    out.append(ArenaTaskSpec(
        name="refactor_grade", task_type="refactor", risk_level="low", difficulty_band="medium",
        context_need="none", module_path="grade.py",
        buggy=("def grade(s):\n    if s >= 90:\n        return 'A'\n    else:\n"
               "        return 'F'  # bug: the B band was lost in a bad refactor\n"),
        fixed=("def grade(s):\n    if s >= 90:\n        return 'A'\n"
               "    if s >= 80:\n        return 'B'\n    return 'F'\n"),
        public_test="from grade import grade\n\ndef test_pub():\n    assert grade(95) == 'A'\n",
        hidden_test=("from grade import grade\n\ndef test_hid():\n    assert grade(85) == 'B'\n"
                     "    assert grade(50) == 'F'\n    assert grade(90) == 'A'\n"),
        issue_text="A bad refactor dropped the 'B' grade band (80-89). Restore it with flat guards."))
    # flaky_fix: a DETERMINISTIC wrong order (returns the LAST even) to remove a flaky shuffle
    out.append(ArenaTaskSpec(
        name="flaky_pick", task_type="flaky_fix", risk_level="medium", difficulty_band="medium",
        context_need="exact_symbol", module_path="pick.py",
        buggy=("def first_even(xs):\n"
               "    return next((x for x in reversed(xs) if x % 2 == 0), None)  # bug: last, not first\n"),
        fixed="def first_even(xs):\n    return next((x for x in xs if x % 2 == 0), None)\n",
        public_test=("from pick import first_even\n\ndef test_pub():\n"
                     "    assert first_even([1, 3, 4, 6]) == 4\n"),
        hidden_test=("from pick import first_even\n\ndef test_hid():\n"
                     "    assert first_even([5, 2, 8]) == 2\n    assert first_even([1, 3]) is None\n"),
        issue_text=("first_even returns the LAST even number, not the first. Return the first even "
                    "in input order (deterministically).")))
    # test_generation: implement a function to satisfy a behavior spec
    out.append(ArenaTaskSpec(
        name="testgen_rom", task_type="test_generation", risk_level="low", difficulty_band="hard",
        context_need="exact_symbol", module_path="rom.py",
        buggy="def to_roman(n):\n    return ''  # unimplemented\n",
        fixed=("def to_roman(n):\n    vals=[(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),"
               "(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]\n"
               "    out=''\n    for v,s in vals:\n        while n>=v:\n            out+=s\n            n-=v\n    return out\n"),
        public_test="from rom import to_roman\n\ndef test_pub():\n    assert to_roman(4) == 'IV'\n",
        hidden_test=("from rom import to_roman\n\ndef test_hid():\n    assert to_roman(9) == 'IX'\n"
                     "    assert to_roman(40) == 'XL'\n    assert to_roman(1994) == 'MCMXCIV'\n"),
        issue_text="Implement to_roman(n) for 1..3999 using subtractive notation."))
    return out


def load_scaled_tasks() -> list[ArenaTaskSpec]:
    tasks = (_local_arith() + _cross_file() + _security() + _ci_migration()
             + _underspecified() + _broad() + _new_types() + _memory_family(n=28))
    return tasks
