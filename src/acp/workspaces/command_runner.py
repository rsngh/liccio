"""Mediated command execution (charter §1.2, §9.2).

Every subprocess in acp goes through ``CommandRunner``. It enforces:
- timeouts with process-tree termination,
- working-directory containment (cwd must be inside an allowed root),
- env redaction (sensitive keys never logged/stored),
- output truncation with full output stored as an artifact,
- exit-code and resource capture,
- network-policy metadata.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from acp.core.artifacts import ArtifactStore, truncate_with_artifact
from acp.core.errors import CommandSecurityError
from acp.core.redaction import Redactor
from acp.core.time import utcnow
from acp.schemas.workspace import CommandRunRecord


class CommandRunner:
    """Runs commands under policy and returns a ``CommandRunRecord``."""

    def __init__(
        self,
        artifact_store: ArtifactStore | None = None,
        redactor: Redactor | None = None,
        allowed_root: Path | str | None = None,
        default_timeout_s: int = 120,
        max_output_chars: int = 20_000,
    ) -> None:
        self.artifact_store = artifact_store
        self.redactor = redactor or Redactor()
        self.allowed_root = Path(allowed_root).resolve() if allowed_root else None
        self.default_timeout_s = default_timeout_s
        self.max_output_chars = max_output_chars

    def _check_cwd(self, cwd: Path, allow_outside: bool) -> None:
        cwd = cwd.resolve()
        if not cwd.exists():
            raise CommandSecurityError(f"cwd does not exist: {cwd}")
        if (
            self.allowed_root is not None
            and not allow_outside
            and not str(cwd).startswith(str(self.allowed_root))
        ):
            raise CommandSecurityError(f"cwd {cwd} escapes allowed root {self.allowed_root}")

    def _store_output(self, text: str, suffix: str) -> tuple[str, str | None]:
        if self.artifact_store is None:
            # No store: just truncate in place.
            if len(text) <= self.max_output_chars:
                return text, None
            return text[: self.max_output_chars] + "\n...[truncated]...", None
        summary, ref = truncate_with_artifact(
            self.artifact_store, text, max_chars=self.max_output_chars, suffix=suffix
        )
        return summary, (ref.uri if ref else None)

    def run(
        self,
        command: list[str],
        cwd: Path | str,
        timeout_s: int | None = None,
        env: dict[str, str] | None = None,
        allow_network: bool = False,
        max_output_chars: int | None = None,
        allow_cwd_outside_root: bool = False,
        attempt_id: str | None = None,
        trace_id: str | None = None,
        check: bool = False,
    ) -> CommandRunRecord:
        cwd_path = Path(cwd)
        self._check_cwd(cwd_path, allow_cwd_outside_root)
        timeout_s = timeout_s or self.default_timeout_s
        if max_output_chars is not None:
            self.max_output_chars = max_output_chars

        # Build environment. Network policy is advisory metadata here; actual
        # sandboxing (no-network) is enforced by Docker/K8s backends in later
        # phases. We never leak secret values into logs.
        full_env = dict(os.environ if env is None else env)
        sanitized_keys = self.redactor.sanitized_env_keys(full_env)

        started = utcnow()
        t0 = time.monotonic()
        timed_out = False
        exit_code: int | None = None
        stdout, stderr = "", ""

        try:
            proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
                command,
                cwd=str(cwd_path),
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,  # own process group for tree-kill
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_s)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill_tree(proc)
                stdout, stderr = proc.communicate()
                exit_code = None
        except FileNotFoundError as exc:
            stderr = f"command not found: {exc}"
            exit_code = 127

        duration = time.monotonic() - t0

        stdout = self.redactor.redact_text(stdout or "")
        stderr = self.redactor.redact_text(stderr or "")
        stdout_summary, stdout_ref = self._store_output(stdout, ".stdout.log")
        stderr_summary, stderr_ref = self._store_output(stderr, ".stderr.log")

        record = CommandRunRecord(
            attempt_id=attempt_id,
            argv=command,
            cwd=str(cwd_path),
            sanitized_env_keys=sanitized_keys,
            exit_code=exit_code,
            timed_out=timed_out,
            allow_network=allow_network,
            stdout_summary=stdout_summary,
            stderr_summary=stderr_summary,
            stdout_artifact_ref=stdout_ref,
            stderr_artifact_ref=stderr_ref,
            duration_s=duration,
            started_at=started,
            finished_at=utcnow(),
            trace_id=trace_id,
        )

        if check and not timed_out and exit_code not in (0, None):
            raise RuntimeError(f"command failed ({exit_code}): {' '.join(command)}")
        return record

    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
