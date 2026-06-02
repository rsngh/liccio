"""Continuous-learning scheduler (Alpha 9, WS10).

The Alpha pipeline already exposes the individual learning steps — refresh the
capability matrix, recompute OPE, detect drift, snapshot control-plane health —
but nothing runs them *together*, *in order*, *repeatedly*, while surviving a
single step's failure. A cron entry that simply shells the CLI would double-count
on retries and abort the whole batch on the first traceback.

:class:`ContinuousLearningScheduler` is that missing piece. It registers named
jobs (callables returning a :class:`JobRunReport`), runs them in registration
order, and is:

* **idempotent** — re-running ``run_all`` updates per-job state in place; it
  never double-counts a job (one run = one ``runs`` increment);
* **resumable** — per-job :class:`ScheduledJobState` (last run / status / counts)
  persists across ``run_all`` calls so a later run continues from known state;
* **fault-tolerant** — a job that raises is recorded as ``status="error"`` and
  the remaining jobs still run; every registered job yields a report.

:func:`default_jobs` wires the existing :class:`~acp.api.service.AppService`
methods (imported lazily, never at module import) into a ready-to-run job list.
Timestamps go through :func:`acp.core.time.utcnow`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from acp.core.time import isoformat, utcnow

JobStatus = str  # one of: "ok", "error", "skipped"

JobFn = Callable[[], "JobRunReport"]


@dataclass
class JobRunReport:
    """Outcome of a single job run."""

    job: str
    status: JobStatus  # ok | error | skipped
    detail: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job": self.job,
            "status": self.status,
            "detail": self.detail,
            "artifacts": self.artifacts,
        }


@dataclass
class ScheduledJobState:
    """Persisted per-job state across scheduler runs."""

    name: str
    last_run: str | None = None
    last_status: JobStatus | None = None
    runs: int = 0
    failures: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "last_run": self.last_run,
            "last_status": self.last_status,
            "runs": self.runs,
            "failures": self.failures,
        }


class ContinuousLearningScheduler:
    """Run named learning jobs in order, idempotently and fault-tolerantly."""

    def __init__(self) -> None:
        self._jobs: list[tuple[str, JobFn]] = []
        self._state: dict[str, ScheduledJobState] = {}

    def register(self, name: str, fn: JobFn) -> None:
        """Register (or replace) a named job, preserving registration order.

        Re-registering an existing name replaces the callable but keeps the
        accumulated :class:`ScheduledJobState`, so resumability survives a
        re-wire.
        """
        for i, (existing, _) in enumerate(self._jobs):
            if existing == name:
                self._jobs[i] = (name, fn)
                break
        else:
            self._jobs.append((name, fn))
        self._state.setdefault(name, ScheduledJobState(name=name))

    def register_jobs(self, jobs: dict[str, JobFn]) -> None:
        """Register many jobs at once (insertion order preserved)."""
        for name, fn in jobs.items():
            self.register(name, fn)

    def state(self, name: str) -> ScheduledJobState | None:
        return self._state.get(name)

    def states(self) -> list[ScheduledJobState]:
        return [self._state[name] for name, _ in self._jobs]

    def run_all(self) -> list[JobRunReport]:
        """Run every registered job in order, returning one report per job.

        Each job runs exactly once per call (so ``runs`` increments by one,
        never more — the idempotence guarantee). A job that raises is caught,
        recorded as ``status="error"`` with the exception text, and counted as a
        failure; the remaining jobs still run. State is updated in place so a
        subsequent ``run_all`` resumes from the latest counts.
        """
        reports: list[JobRunReport] = []
        for name, fn in self._jobs:
            st = self._state.setdefault(name, ScheduledJobState(name=name))
            try:
                report = fn()
                if not isinstance(report, JobRunReport):
                    report = JobRunReport(
                        job=name,
                        status="error",
                        detail=f"job did not return a JobRunReport (got {type(report).__name__})",
                    )
            except Exception as exc:  # noqa: BLE001 - jobs must never abort the batch
                report = JobRunReport(
                    job=name,
                    status="error",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            report.job = name  # canonical name regardless of what the job set
            st.runs += 1
            st.last_run = isoformat(utcnow())
            st.last_status = report.status
            if report.status == "error":
                st.failures += 1
            reports.append(report)
        return reports

    def to_dict(self) -> dict:
        return {
            "n_jobs": len(self._jobs),
            "jobs": [name for name, _ in self._jobs],
            "state": [s.to_dict() for s in self.states()],
        }


def _safe_call(name: str, fn: Callable[[], Any], *, summary_key: str) -> JobRunReport:
    """Invoke ``fn`` defensively, mapping result/exception to a JobRunReport."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - defensive: report, don't raise
        return JobRunReport(job=name, status="error", detail=f"{type(exc).__name__}: {exc}")
    artifacts = result if isinstance(result, dict) else {summary_key: result}
    return JobRunReport(job=name, status="ok", detail=f"{name} completed", artifacts=artifacts)


def default_jobs(service: Any) -> dict[str, JobFn]:
    """Wire existing :class:`~acp.api.service.AppService` methods into jobs.

    The returned mapping is ordered: ``artifact_validation`` →
    ``capability_matrix_refresh`` → ``ope_refresh`` → ``drift_detection`` →
    ``health_snapshot``. Each job is defensive: it calls the matching service
    method *if present* (via :func:`getattr`) and reports ``skipped`` when the
    method is unavailable, ``error`` when it raises, and ``ok`` otherwise. The
    ``service`` is intentionally untyped/lazy so this module never imports
    :class:`AppService` or requires a live DB at import time.
    """

    def _has(method: str) -> Callable[[], Any] | None:
        fn = getattr(service, method, None)
        return fn if callable(fn) else None

    def artifact_validation() -> JobRunReport:
        fn = _has("validate_artifacts") or _has("artifact_validation")
        if fn is None:
            return JobRunReport(
                job="artifact_validation",
                status="skipped",
                detail="no artifact-validation method on service",
            )
        return _safe_call("artifact_validation", fn, summary_key="validation")

    def capability_matrix_refresh() -> JobRunReport:
        fn = _has("build_capability_matrix")
        if fn is None:
            return JobRunReport(
                job="capability_matrix_refresh",
                status="skipped",
                detail="no build_capability_matrix method on service",
            )
        return _safe_call("capability_matrix_refresh", fn, summary_key="matrix")

    def ope_refresh() -> JobRunReport:
        fn = _has("real_log_ope_report") or _has("ope_report")
        if fn is None:
            return JobRunReport(
                job="ope_refresh",
                status="skipped",
                detail="no OPE method on service",
            )
        return _safe_call("ope_refresh", fn, summary_key="ope")

    def drift_detection() -> JobRunReport:
        fn = _has("drift_report")
        if fn is None:
            # Stub is acceptable: report a no-op rather than failing the batch.
            return JobRunReport(
                job="drift_detection",
                status="skipped",
                detail="no drift_report method on service (stub)",
                artifacts={"drift": None},
            )
        return _safe_call("drift_detection", fn, summary_key="drift")

    def health_snapshot() -> JobRunReport:
        fn = _has("control_plane_health") or _has("agents_health")
        if fn is None:
            return JobRunReport(
                job="health_snapshot",
                status="skipped",
                detail="no health method on service",
            )
        return _safe_call("health_snapshot", fn, summary_key="health")

    return {
        "artifact_validation": artifact_validation,
        "capability_matrix_refresh": capability_matrix_refresh,
        "ope_refresh": ope_refresh,
        "drift_detection": drift_detection,
        "health_snapshot": health_snapshot,
    }


__all__ = [
    "ContinuousLearningScheduler",
    "JobRunReport",
    "ScheduledJobState",
    "default_jobs",
]
