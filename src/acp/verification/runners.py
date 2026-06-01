"""Verification runners producing Evidence (charter §14.3, §14.4).

Each runner executes commands through the mediated CommandRunner and parses the
result into Evidence. When a required external CLI is absent, the evidence is
marked SKIPPED with a reason (never PASS).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from acp.core.enums import EvidenceKind, EvidenceStatus
from acp.schemas.verification import Evidence
from acp.workspaces.command_runner import CommandRunner


def _cli_available(argv: list[str]) -> bool:
    return shutil.which(argv[0]) is not None


class BaseRunner:
    kind: EvidenceKind = EvidenceKind.UNIT_TEST
    name: str = "command"

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def _skip(self, task_id: str, attempt_id: str | None, reason: str) -> Evidence:
        return Evidence(
            task_id=task_id, attempt_id=attempt_id, kind=self.kind, name=self.name,
            status=EvidenceStatus.SKIPPED, confidence=0.3, summary=reason,
        )


class PytestRunner(BaseRunner):
    kind = EvidenceKind.UNIT_TEST
    name = "pytest"

    def run(
        self, command: list[str], cwd: Path, task_id: str, attempt_id: str | None = None
    ) -> Evidence:
        if not _cli_available(command):
            return self._skip(task_id, attempt_id, f"{command[0]} not installed")
        rec = self.runner.run(command, cwd=cwd, allow_cwd_outside_root=True, attempt_id=attempt_id)
        out = f"{rec.stdout_summary}\n{rec.stderr_summary}"
        passed, failed, skipped, errors = self._parse(out)
        if rec.timed_out:
            status = EvidenceStatus.FAIL
        elif rec.exit_code == 0:
            status = EvidenceStatus.PASS
        else:
            status = EvidenceStatus.FAIL
        return Evidence(
            task_id=task_id, attempt_id=attempt_id, kind=self.kind, name=self.name,
            status=status, confidence=0.9,
            summary=f"passed={passed} failed={failed} skipped={skipped} errors={errors}",
            raw_output_ref=rec.stdout_artifact_ref,
            metadata={"passed": passed, "failed": failed, "skipped": skipped, "errors": errors,
                      "exit_code": rec.exit_code, "timed_out": rec.timed_out},
        )

    @staticmethod
    def _parse(output: str) -> tuple[int, int, int, int]:
        passed = failed = skipped = errors = 0
        for m in re.finditer(r"(\d+) (passed|failed|skipped|error[s]?)", output):
            n = int(m.group(1))
            kind = m.group(2)
            if kind == "passed":
                passed = n
            elif kind == "failed":
                failed = n
            elif kind == "skipped":
                skipped = n
            else:
                errors = n
        return passed, failed, skipped, errors


class GenericCommandRunner(BaseRunner):
    kind = EvidenceKind.STATIC_ANALYSIS
    name = "command"

    def __init__(self, runner: CommandRunner, name: str = "command",
                 kind: EvidenceKind = EvidenceKind.STATIC_ANALYSIS) -> None:
        super().__init__(runner)
        self.name = name
        self.kind = kind

    def run(
        self, command: list[str], cwd: Path, task_id: str, attempt_id: str | None = None
    ) -> Evidence:
        if not _cli_available(command):
            return self._skip(task_id, attempt_id, f"{command[0]} not installed")
        rec = self.runner.run(command, cwd=cwd, allow_cwd_outside_root=True, attempt_id=attempt_id)
        if rec.timed_out:
            status = EvidenceStatus.FAIL
            summary = "timed out"
        elif rec.exit_code == 0:
            status = EvidenceStatus.PASS
            summary = "ok"
        else:
            status = EvidenceStatus.FAIL
            summary = f"exit={rec.exit_code}"
        return Evidence(
            task_id=task_id, attempt_id=attempt_id, kind=self.kind, name=self.name,
            status=status, confidence=0.8, summary=summary,
            raw_output_ref=rec.stdout_artifact_ref,
            metadata={"exit_code": rec.exit_code, "timed_out": rec.timed_out},
        )


class SecurityScannerRunner(BaseRunner):
    kind = EvidenceKind.SECURITY_SCAN
    name = "security"

    def run(
        self, command: list[str], cwd: Path, task_id: str, attempt_id: str | None = None
    ) -> Evidence:
        if not _cli_available(command):
            return self._skip(task_id, attempt_id, f"{command[0]} not installed")
        rec = self.runner.run(command, cwd=cwd, allow_cwd_outside_root=True, attempt_id=attempt_id)
        out = f"{rec.stdout_summary}\n{rec.stderr_summary}".lower()
        high = "high" in out and "severity" in out
        if rec.exit_code == 0 and not high:
            status = EvidenceStatus.PASS
        elif high:
            status = EvidenceStatus.FAIL
        else:
            status = EvidenceStatus.WARN
        return Evidence(
            task_id=task_id, attempt_id=attempt_id, kind=self.kind, name=self.name,
            status=status, confidence=0.7,
            summary="high severity findings" if high else "no high severity findings",
            metadata={"high_severity": high, "exit_code": rec.exit_code},
        )


class PlaywrightRunner(BaseRunner):
    kind = EvidenceKind.UI_FLOW
    name = "playwright"

    def run(
        self, command: list[str], cwd: Path, task_id: str, attempt_id: str | None = None
    ) -> Evidence:
        if not _cli_available(command[:1]):
            return self._skip(task_id, attempt_id, "playwright/npx not installed")
        rec = self.runner.run(command, cwd=cwd, allow_cwd_outside_root=True, attempt_id=attempt_id)
        status = EvidenceStatus.PASS if rec.exit_code == 0 else EvidenceStatus.FAIL
        return Evidence(
            task_id=task_id, attempt_id=attempt_id, kind=self.kind, name=self.name,
            status=status, confidence=0.8, summary=f"exit={rec.exit_code}",
            metadata={"exit_code": rec.exit_code},
        )
