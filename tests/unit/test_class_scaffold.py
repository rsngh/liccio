"""P7 W2: class-scope tables + splice round-trip for whole-class repairs."""

from __future__ import annotations

from evals.issue_replay.repair_harness import (
    _class_table,
    _owning_class,
    _parse_classes,
    _splice,
)

_MOD = (
    "import os\n\n"
    "class LRU:\n"
    "    def __init__(self, cap):\n"
    "        self.cap = cap\n"
    "    def get(self, k):\n"
    "        return None\n\n"
    "def helper(x):\n"
    "    return x\n"
)


def test_class_table_and_owners() -> None:
    ctab = _class_table(_MOD)
    assert "LRU" in ctab and ctab["LRU"][0] == 3
    owners = _owning_class(_MOD)
    assert owners["get"] == "LRU" and owners["__init__"] == "LRU"
    assert "helper" not in owners


def test_parse_classes_with_fence() -> None:
    block = "```python\nclass LRU:\n    def get(self, k):\n        return 42\n```"
    out = _parse_classes(block)
    assert list(out) == ["LRU"] and "return 42" in out["LRU"]


def test_class_splice_round_trip() -> None:
    ctab = _class_table(_MOD)
    new_cls = ("class LRU:\n    def __init__(self, cap):\n        self.cap = cap\n"
               "    def get(self, k):\n        return k\n")
    out = _splice(_MOD, ctab, {"LRU": new_cls})
    assert "return k" in out and "return None" not in out
    assert "def helper(x):" in out and "import os" in out      # rest of module untouched
    # spliced module still parses and the class table is recomputable
    assert "LRU" in _class_table(out)
