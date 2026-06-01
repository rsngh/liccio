"""Verification orchestration: run a plan against a workspace -> evidence."""

from __future__ import annotations

from pathlib import Path

from acp.core.enums import EvidenceKind, EvidenceStatus
from acp.schemas.verification import Evidence, VerificationPlan, VerificationRun
from acp.verification.runners import (
    GenericCommandRunner,
    PytestRunner,
    SecurityScannerRunner,
)
from acp.workspaces.command_runner import CommandRunner


class VerificationService:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def run_plan(
        self, plan: VerificationPlan, workspace_path: Path | str, attempt_id: str | None = None
    ) -> tuple[VerificationRun, list[Evidence]]:
        cwd = Path(workspace_path)
        evidence: list[Evidence] = []
        pytest_runner = PytestRunner(self.runner)
        sec_runner = SecurityScannerRunner(self.runner)

        for cmd in plan.required_commands:
            evidence.append(pytest_runner.run(cmd, cwd, plan.task_id, attempt_id))
        for cmd in plan.static_checks:
            name = cmd[0]
            kind = EvidenceKind.TYPE_CHECK if name == "mypy" else EvidenceKind.LINT
            evidence.append(
                GenericCommandRunner(self.runner, name=name, kind=kind).run(
                    cmd, cwd, plan.task_id, attempt_id
                )
            )
        for cmd in plan.security_checks:
            evidence.append(sec_runner.run(cmd, cwd, plan.task_id, attempt_id))
        for cmd in plan.coverage_checks:
            evidence.append(
                GenericCommandRunner(self.runner, name="coverage", kind=EvidenceKind.COVERAGE).run(
                    cmd, cwd, plan.task_id, attempt_id
                )
            )

        overall = (
            EvidenceStatus.FAIL
            if any(
                (EvidenceStatus(e.status) if isinstance(e.status, str) else e.status)
                == EvidenceStatus.FAIL
                for e in evidence
            )
            else EvidenceStatus.PASS
        )
        run = VerificationRun(
            task_id=plan.task_id,
            attempt_id=attempt_id,
            plan_id=plan.id,
            status=overall,
            evidence_ids=[e.id for e in evidence],
        )
        return run, evidence
