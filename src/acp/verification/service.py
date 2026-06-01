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
        self.command_records: list = []

    def run_plan(
        self, plan: VerificationPlan, workspace_path: Path | str, attempt_id: str | None = None
    ) -> tuple[VerificationRun, list[Evidence]]:
        cwd = Path(workspace_path)
        evidence: list[Evidence] = []
        self.command_records = []  # CommandRunRecords produced this plan
        pytest_runner = PytestRunner(self.runner)
        sec_runner = SecurityScannerRunner(self.runner)

        def _collect(runner) -> None:
            if runner.last_record is not None:
                self.command_records.append(runner.last_record)

        for cmd in plan.required_commands:
            evidence.append(pytest_runner.run(cmd, cwd, plan.task_id, attempt_id))
            _collect(pytest_runner)
        for cmd in plan.static_checks:
            name = cmd[0]
            kind = EvidenceKind.TYPE_CHECK if name == "mypy" else EvidenceKind.LINT
            gr = GenericCommandRunner(self.runner, name=name, kind=kind)
            evidence.append(gr.run(cmd, cwd, plan.task_id, attempt_id))
            _collect(gr)
        for cmd in plan.security_checks:
            evidence.append(sec_runner.run(cmd, cwd, plan.task_id, attempt_id))
            _collect(sec_runner)
        for cmd in plan.coverage_checks:
            gr = GenericCommandRunner(self.runner, name="coverage", kind=EvidenceKind.COVERAGE)
            evidence.append(gr.run(cmd, cwd, plan.task_id, attempt_id))
            _collect(gr)

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
