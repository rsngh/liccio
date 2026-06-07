# ruff: noqa: E501  (data-heavy fixture file: inline test sources read better unwrapped)
"""Hard-Realism Arena — task pack (GOALS Alpha 44 P0).

Alpha 43 hit a CEILING: a frontier model solves easy/medium tasks from minimal context, so no
policy beat `cheap_single` with CI separation. These task families are designed to *break* that
ceiling — the fix is genuinely unobtainable from the buggy file alone, so `cheap_single` (minimal
context) provably fails while context-rich strategies (grep / repo_map) succeed. That yields
bucket-level CI-separated wins, the thing Alpha 44 must demonstrate.

Ceiling-breakers:
  - cross_file_nonguessable: the fix must call a helper in an UNREFERENCED file whose value is
    NON-guessable (a random-looking constant). Minimal context can neither guess the value nor
    know the helper exists; grep (sees the file) and repo_map (sees the signature) can.
  - decoy_collision: two same-named symbols in different files; only the right one passes hidden
    tests. Minimal context picks blindly.
  - multi_file_wiring: needs 2-3 unreferenced helpers composed correctly.
  - underspecified: the issue does not say what to do -> the safe move is abstain/spec-needed
    (scored by avoided false-auto-approve, not verified success).
  - security_hidden_exploit: passes public (benign) tests but a hidden exploit test fails on the
    vulnerable version.

Every task ships public + hidden tests and a reference fix proven offline-fair (buggy fails the
hidden test; fix passes public + hidden).
"""

from __future__ import annotations

import hashlib

from evals.metarouter_arena.schema import ArenaTaskSpec


def _factor(seed: str) -> float:
    """A deterministic, non-guessable 4-dp factor in [0.10, 0.99) derived from a seed."""
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return round(0.10 + (h % 9000) / 10000.0, 4)


def _cross_file_nonguessable(n: int = 34) -> list[ArenaTaskSpec]:
    """The primary ceiling-breaker: a non-guessable factor in an unreferenced helper file."""
    out = []
    verbs = [("scale", "multiply x by", lambda x, f: round(x * f, 4)),
             ("offset", "add the adjustment to x", lambda x, f: round(x + f, 4)),
             ("blend", "average x with the reference", lambda x, f: round((x + f) / 2, 4))]
    for i in range(n):
        f = _factor(f"hard-xfile-{i}")
        vname, vdesc, fn = verbs[i % len(verbs)]
        helper = f"policy_{i}.py"      # unreferenced by the buggy module; vague in the issue
        api = "reference_value"
        a, b = 100, 37
        pub_exp = fn(a, f)
        h1, h2 = fn(b, f), fn(250, f)
        buggy = "def compute(x):\n    return round(x * 0.5, 4)  # WRONG: placeholder, not the policy\n"
        fixed = (f"from policy_{i} import {api}\n\n"
                 f"def compute(x):\n    v = {api}()\n    return {('round(x * v, 4)' if vname=='scale' else 'round(x + v, 4)' if vname=='offset' else 'round((x + v) / 2, 4)')}\n")
        out.append(ArenaTaskSpec(
            name=f"xfileNG_{vname}_{i}", task_type="bugfix", risk_level="medium",
            difficulty_band="hard", context_need="cross_file_api", module_path="compute.py",
            buggy=buggy, fixed=fixed,
            public_test=f"from compute import compute\n\ndef test_pub():\n    assert compute({a}) == {pub_exp}\n",
            hidden_test=f"from compute import compute\n\ndef test_hid():\n    assert compute({b}) == {h1}\n    assert compute(250) == {h2}\n",
            issue_text=(f"compute(x) returns the wrong number. It must apply the company's canonical "
                        f"reference policy to x ({vdesc}). The single source of truth lives in this "
                        f"repo's policy module — use it, do not hardcode a value."),
            extra_files={helper: f"def {api}():\n    # canonical, non-obvious policy constant\n    return {f}\n"}))
    return out


def _multi_file_wiring(n: int = 12) -> list[ArenaTaskSpec]:
    """broad_repo_map: compose two unreferenced helpers with non-guessable constants."""
    out = []
    for i in range(n):
        fa, fb = _factor(f"mw-a-{i}"), _factor(f"mw-b-{i}")
        fixed = (f"from base_{i} import base_rate\nfrom adj_{i} import adjustment\n\n"
                 f"def price(x):\n    return round(x * base_rate() + adjustment(), 4)\n")
        out.append(ArenaTaskSpec(
            name=f"multiwire_{i}", task_type="feature", risk_level="medium", difficulty_band="hard",
            context_need="broad_repo_map", module_path="pricing.py",
            buggy="def price(x):\n    return x  # TODO: apply base rate then the adjustment from this repo\n",
            fixed=fixed,
            public_test=f"from pricing import price\n\ndef test_pub():\n    assert price(100) == {round(100*fa+fb,4)}\n",
            hidden_test=f"from pricing import price\n\ndef test_hid():\n    assert price(40) == {round(40*fa+fb,4)}\n    assert price(0) == {round(fb,4)}\n",
            issue_text=("price(x) must multiply x by the repo's base rate and then add the repo's "
                        "adjustment. Both live in this repo as helper functions — compose them; "
                        "do not invent numbers."),
            extra_files={f"base_{i}.py": f"def base_rate():\n    return {fa}\n",
                         f"adj_{i}.py": f"def adjustment():\n    return {fb}\n"}))
    return out


def _decoy_collision(n: int = 10) -> list[ArenaTaskSpec]:
    """exact_symbol with a DECOY: two files define the same-named function; only one is right."""
    out = []
    for i in range(n):
        right, wrong = _factor(f"decoy-r-{i}"), _factor(f"decoy-w-{i}")
        # the issue names the CORRECT module; minimal context (which sees neither) may import the decoy
        fixed = "from rates_official import rate\n\ndef quote(x):\n    return round(x * rate(), 4)\n"
        out.append(ArenaTaskSpec(
            name=f"decoy_{i}", task_type="bugfix", risk_level="medium", difficulty_band="hard",
            context_need="cross_file_api", module_path="quote.py",
            buggy="def quote(x):\n    return round(x * 0.5, 4)  # WRONG placeholder\n",
            fixed=fixed,
            public_test=f"from quote import quote\n\ndef test_pub():\n    assert quote(100) == {round(100*right,4)}\n",
            hidden_test=f"from quote import quote\n\ndef test_hid():\n    assert quote(20) == {round(20*right,4)}\n",
            issue_text=("quote(x) must use the OFFICIAL rate (module `rates_official`), not the "
                        "deprecated one. Apply it to x."),
            extra_files={"rates_official.py": f"def rate():\n    return {right}\n",
                         "rates_legacy.py": f"def rate():\n    return {wrong}  # deprecated, do not use\n"}))
    return out


def _underspecified(n: int = 12) -> list[ArenaTaskSpec]:
    """The issue does not say WHAT to change -> the safe move is abstain/spec-needed."""
    out = []
    for i in range(n):
        out.append(ArenaTaskSpec(
            name=f"underspec_{i}", task_type="bugfix", risk_level="high", difficulty_band="hard",
            context_need="none", module_path=f"mod_{i}.py",
            buggy=f"def handle(x):\n    return x + {i}\n",
            fixed=f"def handle(x):\n    return x + {i}\n",   # no determinable change
            public_test=f"from mod_{i} import handle\n\ndef test_pub():\n    assert handle(0) == {i}\n",
            hidden_test=f"from mod_{i} import handle\n\ndef test_hid():\n    assert handle(0) == {i}\n",
            issue_text="Something seems off here. Please fix it appropriately.",
            forbidden_files=(f"mod_{i}.py",)))   # high-risk vague: changing blind is the wrong move
    return out


def _security_hidden_exploit(n: int = 8) -> list[ArenaTaskSpec]:
    """Passes benign public tests; a hidden exploit test fails on the vulnerable version."""
    out = []
    for i in range(n):
        out.append(ArenaTaskSpec(
            name=f"sec_eval_{i}", task_type="security_fix", risk_level="high", difficulty_band="hard",
            context_need="exact_symbol", module_path="ev.py",
            buggy="def calc(expr):\n    return eval(expr)  # unsafe\n",
            fixed=("import ast, operator\n_O={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}\n"
                   "def calc(expr):\n    def ev(n):\n        if isinstance(n,ast.Constant):\n            return n.value\n"
                   "        if isinstance(n,ast.BinOp):\n            return _O[type(n.op)](ev(n.left),ev(n.right))\n"
                   "        raise ValueError('bad')\n    return ev(ast.parse(expr,mode='eval').body)\n"),
            public_test=f"from ev import calc\n\ndef test_pub():\n    assert calc('{i+1} + 1') == {i+2}\n",
            hidden_test="import pytest\nfrom ev import calc\n\ndef test_hid():\n    assert calc('2*3') == 6\n    with pytest.raises(Exception):\n        calc(\"__import__('os').getcwd()\")\n",
            issue_text="calc() evaluates untrusted input with eval() — an injection risk. Make it a safe arithmetic-only evaluator.",
            forbidden_files=()))
    return out


def _flaky(n: int = 6) -> list[ArenaTaskSpec]:
    out = []
    for i in range(n):
        out.append(ArenaTaskSpec(
            name=f"flaky_{i}", task_type="flaky_fix", risk_level="medium", difficulty_band="medium",
            context_need="exact_symbol", module_path="pk.py",
            buggy="def first_match(xs, k):\n    return next((x for x in reversed(xs) if x % k == 0), None)  # last, not first\n",
            fixed="def first_match(xs, k):\n    return next((x for x in xs if x % k == 0), None)\n",
            public_test=f"from pk import first_match\n\ndef test_pub():\n    assert first_match([1,{2+i},{4+i}], 2) == {(2+i) if (2+i)%2==0 else (4+i)}\n" if False else "from pk import first_match\n\ndef test_pub():\n    assert first_match([1, 4, 8], 2) == 4\n",
            hidden_test="from pk import first_match\n\ndef test_hid():\n    assert first_match([6, 2, 8], 2) == 6\n    assert first_match([1, 3], 2) is None\n",
            issue_text="first_match returns the LAST match, not the first. Return the first in input order."))
    return out


def _memory_repeated(n: int = 10) -> list[ArenaTaskSpec]:
    """memory_required: a recurring off-by-one pagination family (same SHAPE, varied size)."""
    out = []
    for i in range(n):
        sz = (i % 4) + 2
        out.append(ArenaTaskSpec(
            name=f"memrep_{i}", task_type="bugfix", risk_level="low", difficulty_band="medium",
            context_need="memory_required", module_path=f"pg_{i}.py",
            buggy=f"def page(items, p):\n    return items[p*{sz}:(p+1)*{sz}]  # 0-indexed bug\n",
            fixed=f"def page(items, p):\n    return items[(p-1)*{sz}:p*{sz}]\n",
            public_test=f"from pg_{i} import page\n\ndef test_pub():\n    assert page(list(range(40)), 1) == list(range({sz}))\n",
            hidden_test=f"from pg_{i} import page\n\ndef test_hid():\n    assert page(list(range(40)), 2) == list(range({sz}, {2*sz}))\n",
            issue_text=f"page(items, 1) must return the FIRST page of size {sz}; pages are 1-indexed (recurring bug)."))
    return out


def _ci_migration(n: int = 5) -> list[ArenaTaskSpec]:
    out = []
    for i in range(n):
        out.append(ArenaTaskSpec(
            name=f"cimig_{i}", task_type="ci_fix", risk_level="medium", difficulty_band="medium",
            context_need="cross_file_api", module_path="app.py",
            buggy=f"from helpers_{i} import old_fn\n\ndef run(x):\n    return old_fn(x)\n",
            fixed=f"from helpers_{i} import new_fn\n\ndef run(x):\n    return new_fn(x)\n",
            public_test=f"from app import run\n\ndef test_pub():\n    assert run(3) == {3*(i+2)}\n",
            hidden_test=f"from app import run\n\ndef test_hid():\n    assert run(5) == {5*(i+2)}\n    assert run(0) == 0\n",
            issue_text=f"app.py imports old_fn from helpers_{i}, but it was migrated to new_fn (same behavior). Fix the import.",
            extra_files={f"helpers_{i}.py": f"def new_fn(x):\n    return x * {i+2}\n"}))
    return out


def _perf(n: int = 4) -> list[ArenaTaskSpec]:
    out = []
    for i in range(n):
        out.append(ArenaTaskSpec(
            name=f"perf_{i}", task_type="performance", risk_level="low", difficulty_band="medium",
            context_need="exact_symbol", module_path="u.py",
            buggy="def n_unique(xs):\n    out = []\n    for x in xs:\n        out.append(x)  # never dedupes\n    return len(out)\n",
            fixed="def n_unique(xs):\n    return len(set(xs))\n",
            public_test="from u import n_unique\n\ndef test_pub():\n    assert n_unique([1,1,2]) == 2\n",
            hidden_test=f"from u import n_unique\n\ndef test_hid():\n    assert n_unique(list(range({i+5}))*2) == {i+5}\n    assert n_unique([]) == 0\n",
            issue_text="n_unique returns the total count, not the number of unique items. Fix it (prefer O(n))."))
    return out


def _refactor(n: int = 4) -> list[ArenaTaskSpec]:
    out = []
    for i in range(n):
        lo, hi = 60 + i, 80 + i
        out.append(ArenaTaskSpec(
            name=f"refac_{i}", task_type="refactor", risk_level="low", difficulty_band="medium",
            context_need="none", module_path="g.py",
            buggy=f"def grade(s):\n    if s >= {hi}:\n        return 'A'\n    else:\n        return 'F'  # B band dropped\n",
            fixed=f"def grade(s):\n    if s >= {hi}:\n        return 'A'\n    if s >= {lo}:\n        return 'B'\n    return 'F'\n",
            public_test=f"from g import grade\n\ndef test_pub():\n    assert grade({hi+5}) == 'A'\n",
            hidden_test=f"from g import grade\n\ndef test_hid():\n    assert grade({lo+1}) == 'B'\n    assert grade({lo-5}) == 'F'\n",
            issue_text=f"A bad refactor dropped the 'B' band ([{lo},{hi})). Restore it with flat guards."))
    return out


def _testgen(n: int = 4) -> list[ArenaTaskSpec]:
    out = []
    impls = [("dbl", "x*2", lambda x: x*2), ("sq", "x*x", lambda x: x*x),
             ("neg", "-x", lambda x: -x), ("inc", "x+1", lambda x: x+1)]
    for i in range(n):
        nm, expr, fn = impls[i % len(impls)]
        out.append(ArenaTaskSpec(
            name=f"testgen_{nm}_{i}", task_type="test_generation", risk_level="low",
            difficulty_band="medium", context_need="exact_symbol", module_path="t.py",
            buggy="def f(x):\n    return 0  # unimplemented\n",
            fixed=f"def f(x):\n    return {expr}\n",
            public_test=f"from t import f\n\ndef test_pub():\n    assert f(3) == {fn(3)}\n",
            hidden_test=f"from t import f\n\ndef test_hid():\n    assert f(5) == {fn(5)}\n    assert f(0) == {fn(0)}\n",
            issue_text=f"Implement f(x) so that f(3) == {fn(3)} and it follows the obvious rule from the examples."))
    return out


def load_hard_tasks() -> list[ArenaTaskSpec]:
    return (_cross_file_nonguessable() + _multi_file_wiring() + _decoy_collision()
            + _underspecified() + _security_hidden_exploit() + _flaky()
            + _memory_repeated() + _ci_migration() + _perf() + _refactor() + _testgen())
