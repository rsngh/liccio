"""Tests for the productionized continuous-learning scheduler (Alpha 11, WS10)."""

from __future__ import annotations

import pytest

from acp.learning.scheduler import JobRunReport
from acp.learning.scheduler_prod import (
    STATUS_SKIPPED_DEP,
    DependencyError,
    JobDependencyGraph,
    ProductionScheduler,
    SchedulerLock,
)


def _ok(name: str) -> JobRunReport:
    return JobRunReport(job=name, status="ok", detail="done")


def test_topological_order_respects_deps() -> None:
    g = JobDependencyGraph()
    g.register("matrix")
    g.register("ope", deps=["matrix"])
    g.register("drift", deps=["ope"])
    order = g.topological_order()
    assert order.index("matrix") < order.index("ope") < order.index("drift")


def test_topological_order_raises_on_cycle() -> None:
    g = JobDependencyGraph()
    g.register("a", deps=["b"])
    g.register("b", deps=["a"])
    with pytest.raises(DependencyError):
        g.topological_order()


def test_topological_order_raises_on_unknown_dep() -> None:
    g = JobDependencyGraph()
    g.register("a", deps=["ghost"])
    with pytest.raises(DependencyError):
        g.topological_order()


def test_lock_prevents_concurrent_acquire() -> None:
    lock = SchedulerLock()
    assert lock.acquire() is True
    assert lock.acquire() is False  # already held
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_lock_context_manager() -> None:
    lock = SchedulerLock()
    with lock:
        assert lock.held is True
        with pytest.raises(RuntimeError):
            lock.__enter__()
    assert lock.held is False


def test_dep_failure_skips_dependent() -> None:
    sched = ProductionScheduler(max_retries=0)
    sched.register("matrix", lambda: JobRunReport(job="matrix", status="error", detail="boom"))
    sched.register("ope", lambda: _ok("ope"), deps=["matrix"])
    report = sched.run_all()
    by_job = {r.job: r for r in report.reports}
    assert by_job["matrix"].status == "error"
    assert by_job["ope"].status == STATUS_SKIPPED_DEP
    assert "dep" in by_job["ope"].status
    assert "ope" in report.skipped


def test_retry_reruns_transient_failure() -> None:
    calls = {"n": 0}

    def flaky() -> JobRunReport:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return _ok("flaky")

    sched = ProductionScheduler(max_retries=3)
    sched.register("flaky", flaky)
    report = sched.run_all()
    by_job = {r.job: r for r in report.reports}
    assert by_job["flaky"].status == "ok"
    assert calls["n"] == 3
    assert report.retries.get("flaky") == 2


def test_idempotent_resumable_rerun() -> None:
    sched = ProductionScheduler(max_retries=0)
    sched.register("a", lambda: _ok("a"))
    sched.register("b", lambda: _ok("b"), deps=["a"])

    r1 = sched.run_all()
    assert r1.acquired_lock is True
    assert sched.scheduler.state("a").runs == 1
    assert sched.scheduler.state("b").runs == 1

    r2 = sched.run_all()
    assert r2.acquired_lock is True
    # One run per call -> exactly two runs after two calls (idempotent counting).
    assert sched.scheduler.state("a").runs == 2
    assert sched.scheduler.state("b").runs == 2
    assert all(r.status == "ok" for r in r2.reports)


def test_no_op_when_lock_held() -> None:
    lock = SchedulerLock()
    lock.acquire()
    sched = ProductionScheduler(lock=lock, max_retries=0)
    sched.register("a", lambda: _ok("a"))
    report = sched.run_all()
    assert report.acquired_lock is False
    assert report.reports == []
