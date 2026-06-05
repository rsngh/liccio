"""Tool-use RL / format-adherence dataset (Alpha 24 area 12)."""

from __future__ import annotations

from acp.training.tool_format_dataset import (
    ToolCallRecord,
    build_tool_format_dataset,
    format_reward,
    functional_reward,
    harness_activation_summary,
)


def test_binary_rewards() -> None:
    good = ToolCallRecord("openai_harness", "write_file", {"path": "a.py"}, True, True)
    malformed = ToolCallRecord("openai_harness", "", {}, False, False)
    ineffective = ToolCallRecord("openai_harness", "write_file", {}, True, False)
    assert format_reward(good) == 1 and functional_reward(good) == 1
    assert format_reward(malformed) == 0
    assert format_reward(ineffective) == 1 and functional_reward(ineffective) == 0


def test_dataset_counts_malformed_and_rewards() -> None:
    recs = [
        ToolCallRecord("a", "write_file", {"p": "x"}, True, True),
        ToolCallRecord("a", "run", {}, True, False),
        ToolCallRecord("a", "", {}, False, False),
    ]
    ds = build_tool_format_dataset(recs)
    assert len(ds.examples) == 3 and ds.n_malformed == 1
    assert ds.malformed_rate == round(1 / 3, 4)
    assert [e["reward"] for e in ds.examples] == [1, 0, 0]


def test_secret_bearing_example_is_dropped() -> None:
    recs = [ToolCallRecord("a", "run", {"cmd": "echo sk-ABCDEFGHIJKLMNOPQRSTUVWX1234"},
                           True, True)]
    ds = build_tool_format_dataset(recs)
    assert not ds.secret_clean and ds.examples == []  # never exported


def test_jsonl_export_is_clean_lines() -> None:
    ds = build_tool_format_dataset([ToolCallRecord("a", "w", {"p": "x"}, True, True)])
    lines = ds.to_jsonl().splitlines()
    assert len(lines) == 1 and '"reward": 1' in lines[0]


def test_harness_activation_summary() -> None:
    recs = [ToolCallRecord("h", "w", {}, True, True), ToolCallRecord("h", "w", {}, True, False),
            ToolCallRecord("h", "", {}, False, False)]
    s = harness_activation_summary(recs)["h"]
    assert s["har"] == round(2 / 3, 4) and s["hfr"] == round(1 / 3, 4)
