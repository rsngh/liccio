"""Docker live security release-gate runner (alpha-8 WS14).

Runs the enforceable Docker sandbox security checks and writes
``evals/reports/docker_security_live.json``. The production gate
(:class:`acp.evaluation.docker_security_live.DockerSecurityGate`) consults this
report before allowing real-harness execution.

If Docker is unavailable the report is written with an EXPLICIT skipped status
(``available=False``, ``passed=False``, every check listed) so the artifact is
never silently empty and the gate correctly refuses production.

Usage:
    uv run python evals/scripts/run_docker_security_live.py
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.evaluation.docker_security_live import run_docker_security_live

REPORT_DIR = Path("evals/reports")


def main() -> int:
    report = run_docker_security_live()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "docker_security_live.json").write_text(json.dumps(report, indent=2))
    status = "skipped" if report.get("skipped") else ("pass" if report["passed"] else "fail")
    passed = report.get("passed_count", 0)
    total = report.get("total", len(report["checks"]))
    print(f"docker_security_live: status={status} ({passed}/{total})")
    # An explicit skip is a successful run of the gate evidence script; the gate
    # itself (not this runner) is responsible for refusing production.
    return 0 if (report.get("skipped") or report["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
