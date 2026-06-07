"""Headless OpenHands (V1 SDK) driver — LOCAL runtime, no Docker.

Run with the ISOLATED OpenHands venv interpreter (its deps conflict with the project's), as a
subprocess, as the sandboxed `claude` user:

    /tmp/ohvenv/bin/python -m evals.harness_arena.openhands_driver <repo> <model> <prompt>

It drives OpenHands' local workspace agent (terminal/file_editor/grep tools running on the host)
to fix the repo in place, then prints one JSON status line. The arena verifies the result itself
with the held-out hidden test. Backed by any litellm model id (e.g. ``gemini/gemini-2.5-flash``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    repo, model, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
    os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
    from openhands.sdk import LLM, Conversation, LocalWorkspace
    from openhands.tools.preset.default import get_default_agent

    key = os.environ.get("GEMINI_API_KEY") if model.startswith("gemini") else \
        os.environ.get("ANTHROPIC_API_KEY")
    llm = LLM(model=model, api_key=key, usage_id="harness-arena")
    agent = get_default_agent(llm=llm, cli_mode=True)
    ws = LocalWorkspace(working_dir=str(Path(repo)))
    conv = Conversation(agent=agent, workspace=ws, max_iteration_per_run=20)
    status = {"ok": False, "error": None}
    try:
        conv.send_message(prompt)
        conv.run()
        status["ok"] = True
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)[:300]
    print("OH_STATUS " + json.dumps(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
