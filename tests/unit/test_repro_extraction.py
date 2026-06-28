# ruff: noqa: E501
"""P12 W4: fenced-code extraction for synthesized repros must not eat leading code chars (no I/O)."""

from __future__ import annotations

from evals.issue_replay.swebench_verify_stop import _first_block, _strip_lang


def test_strip_lang_preserves_code() -> None:
    # 'python\n' is 7 chars; the old p[9:] chopped 2 real chars off the body -> SyntaxError
    assert _strip_lang('python\n"""doc"""\nimport os') == '"""doc"""\nimport os'
    assert _strip_lang('py\nimport os') == "import os"
    assert _strip_lang("import os") == "import os"          # no language tag -> untouched


def test_first_block_extracts_intact_test() -> None:
    raw = 'Sure:\n```python\n"""repro."""\nimport tempfile\ndef test_bug():\n    assert 1 == 1\n```\ndone'
    body = _first_block(raw)
    assert body.startswith('"""repro."""')                  # leading chars intact (was '"repro..."')
    assert "import tempfile" in body and "def test_bug" in body


def test_first_block_requires_a_test() -> None:
    assert _first_block("```python\nx = 1\n```") == ""       # no def test -> rejected
    assert _first_block("no fence, no test") == ""


def test_first_block_picks_longest_block() -> None:
    raw = "```python\ndef test_a(): pass\n```\n```python\ndef test_long():\n    assert True\n    assert True\n```"
    assert "test_long" in _first_block(raw)
