"""Generate the multi-harness no-patch bakeoff artifact (round-4 Block F / I).

By default runs the deterministic patch + fake baselines so the artifact is
reproducible with no API keys. With --live it adds the real OpenAI and Claude
harnesses (requires the SDKs + ACP_OPENAI_API_KEY / ACP_ANTHROPIC_API_KEY).

    uv run python evals/scripts/run_multi_harness_bakeoff.py
    uv run python evals/scripts/run_multi_harness_bakeoff.py --live

Writes evals/reports/multi_harness_trace_bakeoff.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from acp.agents.fake import FakeAgentAdapter
from acp.agents.patch_agent import PatchAgentAdapter
from acp.evaluation.multi_harness_bakeoff import bakeoff_to_markdown, run_multi_harness_bakeoff

REPORT_DIR = Path("evals/reports")


def build_factories(live: bool) -> dict:
    factories: dict = {"patch": PatchAgentAdapter, "fake": FakeAgentAdapter}
    if live:
        from acp.agents.claude_harness import ClaudeHarnessAdapter
        from acp.agents.openai_harness import OpenAIHarnessAdapter
        factories["openai_harness"] = lambda: OpenAIHarnessAdapter(max_steps=6)
        factories["claude_harness"] = lambda: ClaudeHarnessAdapter(max_steps=6)
    return factories


def main(argv: list[str]) -> int:
    live = "--live" in argv
    report = run_multi_harness_bakeoff(build_factories(live))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "multi_harness_trace_bakeoff.json").write_text(json.dumps(report, indent=2))
    (REPORT_DIR / "multi_harness_trace_bakeoff.md").write_text(bakeoff_to_markdown(report))
    s = report["summary"]
    print(f"multi_harness_bakeoff: live={live} cells={s['n_cells']} "
          f"solve_rate={s['solve_rate']} taxonomy={report['failure_taxonomy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
