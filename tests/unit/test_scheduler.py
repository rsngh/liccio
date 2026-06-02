"""Unit tests for the continuous-learning scheduler (Alpha 9, WS10)."""

from __future__ import annotations

from collections.abc import Callable

from acp.learning.scheduler import (
    ContinuousLearningScheduler,
    JobRunReport,
    default_jobs,
)


def test_runs_all_jobs_in_order() -> None:
    order: list[str] = []

    def make(name: str) -> Callable[[], JobRunReport]:
        def job() -> JobRunReport:
            order.append(name)
            return JobRunReport(job=name, status="ok", detail=f"{name} ran")
        return job

    sched = ContinuousLearningScheduler()
    for name in ("a", "b", "c"):
        sched.register(name, make(name))

    reports = sched.run_all()

    assert order == ["a", "b", "c"]
    assert [r.job for r in reports] == ["a", "b", "c"]
    assert all(r.status == "ok" for r in reports)


def test_failing_job_does_not_abort_batch() -> None:
    ran: list[str] = []

    def ok_job() -> JobRunReport:
        ran.append("ok")
        return JobRunReport(job="ok", status="ok")

    def boom() -> JobRunReport:
        ran.append("boom")
        raise RuntimeError("kaboom")

    def after() -> JobRunReport:
        ran.append("after")
        return JobRunReport(job="after", status="ok")

    sched = ContinuousLearningScheduler()
    sched.register("ok", ok_job)
    sched.register("boom", boom)
    sched.register("after", after)

    reports = sched.run_all()

    assert ran == ["ok", "boom", "after"]
    by_name = {r.job: r for r in reports}
    assert by_name["boom"].status == "error"
    assert "kaboom" in by_name["boom"].detail
    assert by_name["ok"].status == "ok"
    assert by_name["after"].status == "ok"
    # every registered job produced a report
    assert set(by_name) == {"ok", "boom", "after"}


def test_rerun_is_idempotent() -> None:
    def job() -> JobRunReport:
        return JobRunReport(job="x", status="ok")

    def bad() -> JobRunReport:
        raise ValueError("nope")

    sched = ContinuousLearningScheduler()
    sched.register("x", job)
    sched.register("bad", bad)

    sched.run_all()
    sched.run_all()
    sched.run_all()

    st = sched.state("x")
    assert st is not None
    assert st.runs == 3  # one increment per run_all, never double-counted
    assert st.last_status == "ok"
    assert st.failures == 0

    bad_st = sched.state("bad")
    assert bad_st is not None
    assert bad_st.runs == 3
    assert bad_st.failures == 3
    assert bad_st.last_status == "error"


def test_default_jobs_are_defensive_on_bare_service() -> None:
    class _Bare:
        """A stand-in service with no learning methods."""

    sched = ContinuousLearningScheduler()
    sched.register_jobs(default_jobs(_Bare()))

    reports = sched.run_all()

    assert [r.job for r in reports] == [
        "artifact_validation",
        "capability_matrix_refresh",
        "ope_refresh",
        "drift_detection",
        "health_snapshot",
    ]
    # missing methods -> skipped, never error, never crash
    assert all(r.status == "skipped" for r in reports)


def test_default_jobs_invoke_present_methods() -> None:
    class _Stub:
        def build_capability_matrix(self) -> dict:
            return {"n_cells": 3}

        def real_log_ope_report(self) -> dict:
            return {"estimate": 0.5}

        def control_plane_health(self) -> dict:
            return {"healthy": True}

    sched = ContinuousLearningScheduler()
    sched.register_jobs(default_jobs(_Stub()))
    reports = {r.job: r for r in sched.run_all()}

    assert reports["capability_matrix_refresh"].status == "ok"
    assert reports["capability_matrix_refresh"].artifacts == {"n_cells": 3}
    assert reports["ope_refresh"].status == "ok"
    assert reports["health_snapshot"].status == "ok"
    assert reports["artifact_validation"].status == "skipped"
    assert reports["drift_detection"].status == "skipped"
