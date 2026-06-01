"""Sandbox red-team lab runner (round-5 WS10).

Probes the workspace sandbox and writes evals/reports/sandbox_redteam.json.
Local backend safe probes always run; the Docker section runs live when Docker
is available, else records an explicit skip.

    uv run python evals/scripts/run_sandbox_redteam.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acp.evaluation.sandbox_redteam import run_sandbox_redteam

REPORT = Path("evals/reports/sandbox_redteam.json")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="acp_redteam_")) / "ws"
    report = run_sandbox_redteam(root)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))
    local = report["local"]
    print(f"sandbox redteam: local enforced {local['enforced']}/{local['total_enforceable']} "
          f"safe probes; unsafe_for_true_harness={local['unsafe_for_true_harness']}; "
          f"docker={report['docker']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
