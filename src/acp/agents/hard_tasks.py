"""Genuinely hard bugfix tasks to escape the easy-task ceiling (Alpha 25, test F).

The round-24 review notes that strong models are at ceiling on the easy synthetic tasks, so
best-of-k and advisor withhold compute and show no uplift. These tasks are designed so a
weak model fails a meaningful share of single-shot attempts: each buggy module uses a
plausible-but-wrong GREEDY approach to a problem that actually requires dynamic programming
(the classic greedy trap). A blind weak model must recognise the algorithmic flaw and
reimplement the DP — which it does not always get right in one shot, so best-of-k +
execution selection and advisor escalation can finally show non-ceiling value.

Every task ships a reference fix and is proven offline (buggy fails, fix passes) like the
graded suite, so the live measurement is fair.
"""

from __future__ import annotations

from acp.agents.benchmark_suite import BenchTask

# --- coin change: greedy fails on non-canonical coin systems --------------------------
_COIN_BUGGY = (
    "def coin_change(coins, amount):\n"
    "    coins = sorted(coins, reverse=True)\n"
    "    count = 0\n"
    "    for c in coins:  # bug: greedy is wrong for non-canonical coins\n"
    "        count += amount // c\n"
    "        amount %= c\n"
    "    return count if amount == 0 else -1\n"
)
_COIN_FIXED = (
    "def coin_change(coins, amount):\n"
    "    inf = float('inf')\n"
    "    dp = [0] + [inf] * amount\n"
    "    for a in range(1, amount + 1):\n"
    "        for c in coins:\n"
    "            if c <= a:\n"
    "                dp[a] = min(dp[a], dp[a - c] + 1)\n"
    "    return dp[amount] if dp[amount] != inf else -1\n"
)
_COIN_TEST = (
    "from coinchange import coin_change\n\n"
    "def test_coin_change():\n"
    "    assert coin_change([1, 2, 5], 11) == 3\n"
    "    assert coin_change([2], 3) == -1\n"
    "    assert coin_change([1], 0) == 0\n"
    "    assert coin_change([1, 3, 4], 6) == 2\n"      # greedy gives 3 (4+1+1)
    "    assert coin_change([186, 419, 83, 408], 6249) == 20\n"
)

# --- word break: greedy longest-match fails ------------------------------------------
_WB_BUGGY = (
    "def word_break(s, words):\n"
    "    words = set(words)\n"
    "    i = 0\n"
    "    while i < len(s):  # bug: greedy longest match, no backtracking\n"
    "        matched = False\n"
    "        for j in range(len(s), i, -1):\n"
    "            if s[i:j] in words:\n"
    "                i = j\n"
    "                matched = True\n"
    "                break\n"
    "        if not matched:\n"
    "            return False\n"
    "    return True\n"
)
_WB_FIXED = (
    "def word_break(s, words):\n"
    "    words = set(words)\n"
    "    dp = [True] + [False] * len(s)\n"
    "    for i in range(1, len(s) + 1):\n"
    "        for j in range(i):\n"
    "            if dp[j] and s[j:i] in words:\n"
    "                dp[i] = True\n"
    "                break\n"
    "    return dp[len(s)]\n"
)
_WB_TEST = (
    "from wordbreak import word_break\n\n"
    "def test_word_break():\n"
    "    assert word_break('leetcode', ['leet', 'code']) is True\n"
    "    assert word_break('cars', ['car', 'ca', 'rs']) is True\n"      # greedy trap
    "    assert word_break('catsandog', ['cats', 'dog', 'sand', 'and', 'cat']) is False\n"
    "    assert word_break('applepenapple', ['apple', 'pen']) is True\n"
)

# --- longest increasing subsequence: counts consecutive run instead of subsequence ----
_LIS_BUGGY = (
    "def lis(xs):\n"
    "    if not xs:\n        return 0\n"
    "    best = cur = 1\n"
    "    for i in range(1, len(xs)):  # bug: only counts CONSECUTIVE increasing runs\n"
    "        if xs[i] > xs[i - 1]:\n"
    "            cur += 1\n            best = max(best, cur)\n"
    "        else:\n            cur = 1\n"
    "    return best\n"
)
_LIS_FIXED = (
    "def lis(xs):\n"
    "    if not xs:\n        return 0\n"
    "    dp = [1] * len(xs)\n"
    "    for i in range(len(xs)):\n"
    "        for j in range(i):\n"
    "            if xs[j] < xs[i]:\n"
    "                dp[i] = max(dp[i], dp[j] + 1)\n"
    "    return max(dp)\n"
)
_LIS_TEST = (
    "from lis import lis\n\n"
    "def test_lis():\n"
    "    assert lis([1, 3, 2, 4]) == 3\n"          # consecutive-run gives 2
    "    assert lis([10, 9, 2, 5, 3, 7, 101, 18]) == 4\n"
    "    assert lis([7, 7, 7, 7]) == 1\n"
    "    assert lis([]) == 0\n"
    "    assert lis([1, 3, 6, 7, 9, 4, 10, 5, 6]) == 6\n"
)

# --- max product subarray: must track min (negatives flip sign) -----------------------
_MP_BUGGY = (
    "def max_product(xs):\n"
    "    best = cur = xs[0]\n"
    "    for x in xs[1:]:  # bug: ignores that a negative*min can become the max\n"
    "        cur = max(x, cur * x)\n"
    "        best = max(best, cur)\n"
    "    return best\n"
)
_MP_FIXED = (
    "def max_product(xs):\n"
    "    best = mx = mn = xs[0]\n"
    "    for x in xs[1:]:\n"
    "        cands = (x, mx * x, mn * x)\n"
    "        mx, mn = max(cands), min(cands)\n"
    "        best = max(best, mx)\n"
    "    return best\n"
)
_MP_TEST = (
    "from maxprod import max_product\n\n"
    "def test_max_product():\n"
    "    assert max_product([2, 3, -2, 4]) == 6\n"
    "    assert max_product([-2, 3, -4]) == 24\n"      # buggy misses this
    "    assert max_product([-2, 0, -1]) == 0\n"
    "    assert max_product([2, -5, -2, -4, 3]) == 24\n"
)

# --- min path sum: greedy descent is not optimal --------------------------------------
_MPS_BUGGY = (
    "def min_path_sum(grid):\n"
    "    i = j = 0\n"
    "    total = grid[0][0]\n"
    "    rows, cols = len(grid), len(grid[0])\n"
    "    while i < rows - 1 or j < cols - 1:  # bug: greedy local choice is not optimal\n"
    "        down = grid[i + 1][j] if i + 1 < rows else float('inf')\n"
    "        right = grid[i][j + 1] if j + 1 < cols else float('inf')\n"
    "        if down < right:\n            i += 1\n            total += down\n"
    "        else:\n            j += 1\n            total += right\n"
    "    return total\n"
)
_MPS_FIXED = (
    "def min_path_sum(grid):\n"
    "    rows, cols = len(grid), len(grid[0])\n"
    "    dp = [[0] * cols for _ in range(rows)]\n"
    "    for i in range(rows):\n"
    "        for j in range(cols):\n"
    "            if i == 0 and j == 0:\n                dp[i][j] = grid[i][j]\n"
    "            elif i == 0:\n                dp[i][j] = dp[i][j - 1] + grid[i][j]\n"
    "            elif j == 0:\n                dp[i][j] = dp[i - 1][j] + grid[i][j]\n"
    "            else:\n                dp[i][j] = min(dp[i - 1][j], dp[i][j - 1]) + grid[i][j]\n"
    "    return dp[-1][-1]\n"
)
_MPS_TEST = (
    "from minpath import min_path_sum\n\n"
    "def test_min_path_sum():\n"
    "    assert min_path_sum([[1, 3, 1], [1, 5, 1], [4, 2, 1]]) == 7\n"  # greedy gives 9
    "    assert min_path_sum([[1, 2, 3], [4, 5, 6]]) == 12\n"
    "    assert min_path_sum([[5]]) == 5\n"
)


def _t(name, mod, buggy, fixed, test):
    prompt = (f"There is a bug in {mod}: it uses a greedy approach that is not correct for "
              f"all inputs. Fix the algorithm so the tests pass, then run "
              f"`python -m pytest -q`.")
    return BenchTask(name, "hard", mod, buggy, fixed, test, prompt)


HARD_TASKS: list[BenchTask] = [
    _t("coin_change", "coinchange.py", _COIN_BUGGY, _COIN_FIXED, _COIN_TEST),
    _t("word_break", "wordbreak.py", _WB_BUGGY, _WB_FIXED, _WB_TEST),
    _t("lis", "lis.py", _LIS_BUGGY, _LIS_FIXED, _LIS_TEST),
    _t("max_product", "maxprod.py", _MP_BUGGY, _MP_FIXED, _MP_TEST),
    _t("min_path_sum", "minpath.py", _MPS_BUGGY, _MPS_FIXED, _MPS_TEST),
]
