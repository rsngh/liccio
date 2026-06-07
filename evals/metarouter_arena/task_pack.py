"""MetaRouter Arena — unseen task pack (GOALS Alpha 42 P0).

Tasks authored fresh for the arena (not present elsewhere in src/ or tests/), spanning the
``context_need`` dimension so context-routing policies (grep / repo_map / hybrid / memory) can
be differentiated from blind ones. Each ships a buggy module + a VISIBLE public test + a
HELD-OUT hidden test (different inputs) + the reference fix (offline fairness only).
"""

from __future__ import annotations

from evals.metarouter_arena.schema import ArenaTaskSpec

# --- context_need = none: self-contained single-file bug -------------------------------
_BACKOFF = ArenaTaskSpec(
    name="retry_backoff", task_type="bugfix", risk_level="low", difficulty_band="easy",
    context_need="none", module_path="backoff.py",
    buggy="def retry_delay(base, attempt):\n    return base * attempt  # linear, not exponential\n",
    fixed="def retry_delay(base, attempt):\n    return base * (2 ** attempt)\n",
    public_test=("from backoff import retry_delay\n\n"
                 "def test_pub():\n    assert retry_delay(1.0, 3) == 8.0\n"),
    hidden_test=("from backoff import retry_delay\n\n"
                 "def test_hid():\n    assert retry_delay(1.0, 4) == 16.0\n"
                 "    assert retry_delay(0.5, 3) == 4.0\n"
                 "    assert retry_delay(1.0, 10) == 1024.0\n"),
    issue_text=("retry_delay(1, 3) returns 3 but exponential backoff should give 8 "
                "(base * 2**attempt). Delays grow linearly instead of exponentially."))

# --- context_need = exact_symbol: fix needs one symbol's exact behavior (grep-friendly) -
_SLUG = ArenaTaskSpec(
    name="slug_trim", task_type="bugfix", risk_level="low", difficulty_band="medium",
    context_need="exact_symbol", module_path="slug.py",
    buggy=("import re\n\ndef slugify(s):\n    s = s.lower()\n"
           "    return re.sub(r'[^a-z0-9]+', '-', s)  # keeps leading/trailing dashes\n"),
    fixed=("import re\n\ndef slugify(s):\n    s = s.strip().lower()\n"
           "    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')\n"),
    public_test=("from slug import slugify\n\n"
                 "def test_pub():\n    assert slugify('Hello World') == 'hello-world'\n"),
    hidden_test=("from slug import slugify\n\n"
                 "def test_hid():\n    assert slugify('  Trim Me  ') == 'trim-me'\n"
                 "    assert slugify('a!!!b') == 'a-b'\n    assert slugify('--x--') == 'x'\n"),
    issue_text="slugify('  Trim Me  ') yields '-trim-me-'; it must strip surrounding separators.")

# --- context_need = cross_file_api: must CALL an API defined elsewhere (repo_map wins) ---
_DISCOUNTS = ("def apply_house_discount(price):\n"
              "    # canonical house policy — single source of truth\n"
              "    return round(price * 0.87, 2)\n")
_CHECKOUT = ArenaTaskSpec(
    name="checkout_discount", task_type="bugfix", risk_level="medium", difficulty_band="hard",
    context_need="cross_file_api", module_path="checkout.py",
    buggy=("def checkout_total(price):\n"
           "    return round(price * 0.90, 2)  # hardcoded wrong discount\n"),
    fixed=("from discounts import apply_house_discount\n\n"
           "def checkout_total(price):\n    return apply_house_discount(price)\n"),
    public_test=("from checkout import checkout_total\n\n"
                 "def test_pub():\n    assert checkout_total(100) == 87.0\n"),
    hidden_test=("from checkout import checkout_total\n\n"
                 "def test_hid():\n    assert checkout_total(50) == 43.5\n"
                 "    assert checkout_total(200) == 174.0\n"),
    issue_text=("checkout_total(100) is wrong. It must apply the company's canonical house "
                "discount policy (the single source of truth lives in the discounts module), "
                "not a hardcoded number."),
    extra_files={"discounts.py": _DISCOUNTS})

# --- context_need = broad_repo_map: fix needs awareness of several modules' APIs ---------
_PIPE_VALIDATE = "def validate(record):\n    return 'id' in record and 'amount' in record\n"
_PIPE_NORMALIZE = ("def normalize(record):\n"
                   "    return {**record, 'amount': float(record['amount'])}\n")
_PIPELINE = ArenaTaskSpec(
    name="pipeline_wire", task_type="feature", risk_level="medium", difficulty_band="hard",
    context_need="broad_repo_map", module_path="pipeline.py",
    buggy=("def process(record):\n"
           "    return record  # TODO: validate then normalize using the existing helpers\n"),
    fixed=("from validate import validate\nfrom normalize import normalize\n\n"
           "def process(record):\n"
           "    if not validate(record):\n        raise ValueError('invalid record')\n"
           "    return normalize(record)\n"),
    public_test=("from pipeline import process\n\n"
                 "def test_pub():\n"
                 "    assert process({'id': 1, 'amount': '5'}) == {'id': 1, 'amount': 5.0}\n"),
    hidden_test=("import pytest\nfrom pipeline import process\n\n"
                 "def test_hid():\n"
                 "    assert process({'id': 9, 'amount': '2.5'}) == {'id': 9, 'amount': 2.5}\n"
                 "    with pytest.raises(ValueError):\n        process({'id': 1})\n"),
    issue_text=("process() should validate a record then normalize it, REUSING the existing "
                "validate and normalize helpers in this repo (do not reimplement them). Invalid "
                "records must raise ValueError."),
    extra_files={"validate.py": _PIPE_VALIDATE, "normalize.py": _PIPE_NORMALIZE})

# --- underspecified: two bugs, only one named (test-discipline) -------------------------
_STATS = ArenaTaskSpec(
    name="stats_two_bug", task_type="bugfix", risk_level="medium", difficulty_band="hard",
    context_need="none", module_path="stats.py",
    buggy=("def mean(xs):\n    return sum(xs) // len(xs)  # integer division\n\n"
           "def median(xs):\n    n = len(xs)\n"
           "    return xs[n // 2]  # unsorted + wrong for even n\n"),
    fixed=("def mean(xs):\n    return sum(xs) / len(xs)\n\n"
           "def median(xs):\n    s = sorted(xs)\n    n = len(s)\n"
           "    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2\n"),
    public_test=("from stats import mean\n\n"
                 "def test_pub():\n    assert mean([1, 2, 3, 4]) == 2.5\n"),
    hidden_test=("from stats import mean, median\n\n"
                 "def test_hid():\n    assert mean([1, 2, 3, 4]) == 2.5\n"
                 "    assert median([3, 1, 2]) == 2\n    assert median([1, 2, 3, 4]) == 2.5\n"),
    issue_text=("mean([1,2,3,4]) should be 2.5 but isn't. Fix it. (Run the full test suite and "
                "fix every failure before finishing.)"))

TASK_PACK: list[ArenaTaskSpec] = [_BACKOFF, _SLUG, _CHECKOUT, _PIPELINE, _STATS]
