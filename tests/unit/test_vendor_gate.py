"""Vendor-native live gate invariants (GOALS Alpha 42 P9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPORT = Path("reports/vendor_native_live_gate.json")


@pytest.mark.skipif(not _REPORT.exists(), reason="vendor gate report not built")
def test_unavailable_adapters_are_discoverable_but_not_routed() -> None:
    rep = json.loads(_REPORT.read_text())
    # every required adapter is present (discoverable), even when unavailable
    names = {a["adapter"] for a in rep["adapters"]}
    assert {"openai_harness", "codex_cli", "openhands"} <= names
    # no unavailable adapter is routed by default (availability != capability)
    for a in rep["adapters"]:
        if not a["available"]:
            assert not a["routed_by_default"]
            assert a["reason"]                       # an actionable reason is given
    assert rep["availability_separated_from_capability"] is True
    assert rep["no_unavailable_adapter_routed_by_default"] is True


@pytest.mark.skipif(not _REPORT.exists(), reason="vendor gate report not built")
def test_live_harness_activation_matrix_present() -> None:
    rep = json.loads(_REPORT.read_text())
    if "claude_harness" in rep["live_capable"] and rep["activation_matrix"]:
        m = rep["activation_matrix"]["claude_harness"]
        assert 0.0 <= m["HAR"] <= 1.0 and 0.0 <= m["HFR"] <= 1.0 and 0.0 <= m["PWL"] <= 1.0
