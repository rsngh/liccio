"""Continuous-learning scheduler productionization (Alpha 11, WS10).

Alpha-9 :class:`~acp.learning.scheduler.ContinuousLearningScheduler` runs named
learning jobs in *registration* order, idempotently and fault-tolerantly. That
is enough for a flat batch but not for production: real learning jobs have
*dependencies* (you cannot recompute OPE before the capability matrix refresh
has landed), a cron-triggered batch must not run *concurrently* with itself, a
transiently-failing job deserves a *retry*, and a downstream job whose
dependency failed must be *skipped* rather than run on stale inputs.

This module adds those guarantees on top of the existing scheduler, on new code
only:

* :class:`JobDependencyGraph` — declare ``job -> deps`` edges and obtain a
  :meth:`~JobDependencyGraph.topological_order` (raising on a cycle); a job is
  eligible only after every dependency has *succeeded*.
* :class:`SchedulerLock` — a single-writer in-memory token lock with
  ``acquire`` / ``release`` and a context-manager API; a second acquire while
  held returns ``False``.
* :class:`ProductionScheduler` — composes the three. :meth:`run_all` runs jobs
  in dependency order under the lock, skips jobs whose deps failed
  (``status="skipped:dep"``), retries a flaky job up to ``max_retries`` times,
  flags stale reports, and is idempotent + resumable.

Timestamps go through :func:`acp.core.time.utcnow`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from types import TracebackType

from acp.core.time import isoformat, utcnow
from acp.learning.scheduler import (
    ContinuousLearningScheduler,
    JobFn,
    JobRunReport,
)

# Statuses the productionized scheduler may assign beyond the base ok/error.
STATUS_SKIPPED_DEP = "skipped:dep"


class DependencyError(ValueError):
    """Raised on an unknown dependency or a dependency cycle."""


class JobDependencyGraph:
    """A DAG of ``job -> {deps}`` edges with topological ordering."""

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}

    def register(self, name: str, deps: Iterable[str] = ()) -> None:
        """Register (or replace) a job and its dependency set."""
        self._deps[name] = set(deps)

    def deps(self, name: str) -> set[str]:
        return set(self._deps.get(name, set()))

    def jobs(self) -> list[str]:
        return list(self._deps)

    def topological_order(self) -> list[str]:
        """Return jobs in dependency order; raise :class:`DependencyError` on a cycle.

        Kahn's algorithm over the declared edges. Ties are broken by
        registration order so the result is deterministic. An edge to an
        unregistered job is a :class:`DependencyError`.
        """
        for name, deps in self._deps.items():
            for d in deps:
                if d not in self._deps:
                    raise DependencyError(
                        f"job {name!r} depends on unregistered job {d!r}"
                    )
        order: list[str] = []
        remaining = {n: set(d) for n, d in self._deps.items()}
        registration = list(self._deps)
        while remaining:
            ready = [n for n in registration if n in remaining and not remaining[n]]
            if not ready:
                raise DependencyError(
                    f"dependency cycle among {sorted(remaining)}"
                )
            for n in ready:
                order.append(n)
                del remaining[n]
                for deps in remaining.values():
                    deps.discard(n)
        return order


class SchedulerLock:
    """A single-writer in-memory token lock.

    A second :meth:`acquire` while the lock is held returns ``False`` (it does
    not block), so a concurrent scheduler invocation can detect contention and
    bail. Usable as a context manager; ``__enter__`` acquires and raises
    :class:`RuntimeError` if the lock is already held.
    """

    def __init__(self) -> None:
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> bool:
        """Acquire the lock; return ``False`` if already held."""
        if self._held:
            return False
        self._held = True
        return True

    def release(self) -> None:
        """Release the lock (idempotent)."""
        self._held = False

    def __enter__(self) -> SchedulerLock:
        if not self.acquire():
            raise RuntimeError("scheduler lock already held")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


@dataclass
class ProductionRunReport:
    """Structured outcome of a :meth:`ProductionScheduler.run_all` invocation."""

    started_at: str
    finished_at: str
    acquired_lock: bool
    order: list[str]
    reports: list[JobRunReport] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    retries: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "acquired_lock": self.acquired_lock,
            "order": list(self.order),
            "reports": [r.to_dict() for r in self.reports],
            "skipped": list(self.skipped),
            "stale": list(self.stale),
            "retries": dict(self.retries),
        }


class ProductionScheduler:
    """Productionized scheduler: dependency-ordered, locked, retrying, resumable."""

    def __init__(
        self,
        *,
        scheduler: ContinuousLearningScheduler | None = None,
        graph: JobDependencyGraph | None = None,
        lock: SchedulerLock | None = None,
        max_retries: int = 2,
        stale_after_runs: int | None = None,
    ) -> None:
        self._scheduler = scheduler or ContinuousLearningScheduler()
        self._graph = graph or JobDependencyGraph()
        self._lock = lock or SchedulerLock()
        self._max_retries = max(0, max_retries)
        self._stale_after_runs = stale_after_runs

    def register(self, name: str, fn: JobFn, deps: Iterable[str] = ()) -> None:
        """Register a job with its callable and dependency set."""
        self._scheduler.register(name, fn)
        self._graph.register(name, deps)

    @property
    def scheduler(self) -> ContinuousLearningScheduler:
        return self._scheduler

    @property
    def graph(self) -> JobDependencyGraph:
        return self._graph

    def _run_one(self, name: str, fn: JobFn) -> tuple[JobRunReport, int]:
        """Run ``fn``, retrying up to ``max_retries`` on error. Returns (report, retries)."""
        report = JobRunReport(job=name, status="error", detail="not run")
        retries = 0
        for attempt in range(self._max_retries + 1):
            try:
                result = fn()
                if isinstance(result, JobRunReport):
                    report = result
                else:
                    report = JobRunReport(
                        job=name,
                        status="error",
                        detail=(
                            "job did not return a JobRunReport "
                            f"(got {type(result).__name__})"
                        ),
                    )
            except Exception as exc:  # noqa: BLE001 - a job must never abort the batch
                report = JobRunReport(
                    job=name,
                    status="error",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            report.job = name
            if report.status != "error":
                break
            if attempt < self._max_retries:
                retries += 1
        return report, retries

    def run_all(self) -> ProductionRunReport:
        """Run jobs in dependency order under the lock; structured report.

        If the lock cannot be acquired the run is a no-op with
        ``acquired_lock=False``. Otherwise jobs run in
        :meth:`JobDependencyGraph.topological_order`; a job whose dependency did
        not succeed is recorded ``status="skipped:dep"`` and its dependents
        cascade-skip. Failing jobs are retried up to ``max_retries``. Per-job
        :class:`~acp.learning.scheduler.ScheduledJobState` is updated in place so
        re-running is idempotent (one run = one ``runs`` increment) and
        resumable. Reports whose owning state already had ``runs`` above
        ``stale_after_runs`` are flagged stale.
        """
        started = isoformat(utcnow())
        if not self._lock.acquire():
            return ProductionRunReport(
                started_at=started,
                finished_at=isoformat(utcnow()),
                acquired_lock=False,
                order=[],
            )
        try:
            order = self._graph.topological_order()
            jobs = dict(self._scheduler._jobs)  # noqa: SLF001
            succeeded: set[str] = set()
            reports: list[JobRunReport] = []
            skipped: list[str] = []
            stale: list[str] = []
            retries: dict[str, int] = {}

            for name in order:
                st = self._scheduler.state(name)
                deps = self._graph.deps(name)
                if not deps.issubset(succeeded):
                    failed = sorted(deps - succeeded)
                    report = JobRunReport(
                        job=name,
                        status=STATUS_SKIPPED_DEP,
                        detail=f"dependency not satisfied: {failed}",
                    )
                    skipped.append(name)
                    if st is not None:
                        st.runs += 1
                        st.last_run = isoformat(utcnow())
                        st.last_status = report.status
                    reports.append(report)
                    continue

                fn = jobs.get(name)
                if fn is None:
                    report = JobRunReport(
                        job=name,
                        status="error",
                        detail="no callable registered for job",
                    )
                    n_retries = 0
                else:
                    report, n_retries = self._run_one(name, fn)
                if n_retries:
                    retries[name] = n_retries
                if st is not None:
                    st.runs += 1
                    st.last_run = isoformat(utcnow())
                    st.last_status = report.status
                    if report.status == "error":
                        st.failures += 1
                    if (
                        self._stale_after_runs is not None
                        and st.runs > self._stale_after_runs
                    ):
                        stale.append(name)
                if report.status == "ok":
                    succeeded.add(name)
                reports.append(report)

            return ProductionRunReport(
                started_at=started,
                finished_at=isoformat(utcnow()),
                acquired_lock=True,
                order=order,
                reports=reports,
                skipped=skipped,
                stale=stale,
                retries=retries,
            )
        finally:
            self._lock.release()


__all__ = [
    "STATUS_SKIPPED_DEP",
    "DependencyError",
    "JobDependencyGraph",
    "ProductionRunReport",
    "ProductionScheduler",
    "SchedulerLock",
]
